# MCCF Day 30 Session Handoff
**Generated:** 2026-05-29 end of Day 30
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. Root cause of displacer failure identified through systematic testing

Built `displacer_test_minimal.x3d` + `displacer_test_harness.html` — a minimal reproducible test that isolated X_ITE HAnim displacer behavior from cindy_v6 complexity.

**Findings in order of discovery:**
- `profile='Full'` → X_ITE parse failure. Use `profile='Interchange'`
- `<!DOCTYPE>` and `xsd:` attributes → parse failure. Strip them.
- `loa='1'` → geometry invisible. Must be `loa='4'`
- Missing `containerField='skeleton'` on root HAnimJoint → geometry invisible
- Missing `TextureCoordinate` in IndexedFaceSet → geometry invisible
- Missing `<component name='Interpolation' level='1'/>` → ROUTEs do not fire
- Missing segment-level `<Coordinate containerField='coord'/>` → displacer has nothing to target
- `HAnimDisplacer.weight` via SAI: accepts writes, readback confirms, **mesh does not deform**
- `HAnimDisplacer.weight` via ROUTE (direct clock→weight): **weight stays 0, ROUTE does not connect**
- Joint rotation via ROUTE (OrientationInterpolator→HAnimJoint): **fires after adding Interpolation component** — subtle movement confirmed

**Conclusion:** HAnimDisplacer deformation does not fire in x_ite@10.5.2 CDN build regardless of structure. The ROUTE system works for joint rotation. It does not work for HAnimDisplacer.weight. This is consistent across all test configurations.

### 2. Decision: Abandon HAnimDisplacer. Use SAI coordinate writes.

**New architecture — SAI Morph Driver:**

Instead of HAnimDisplacer nodes driving geometry, JavaScript reads rest-pose vertex positions and applies AU displacements directly to `Coordinate.point` via SAI.

**At init:**
- Read `Coordinate.point` from each face segment, cache as `restPose[]`
- Load AU displacement table from JSON (served by Flask)
- Displacement table: `{ "JawDrop": { "coordIndex": [4,7,12,...], "displacements": [[0,-0.3,0],...] }, ... }`

**On AU weight change:**
- Start with copy of `restPose[]`
- For each active AU: `for each i in coordIndex: point[i] += displacement[i] * weight`
- Multiple AUs blend additively
- Write modified array back to `Coordinate.point` via SAI

**File size benefit:** Removing HAnimDisplacer infrastructure (1290 ROUTEs, 30 AnimationAdapters, 30 TimeSensors, 65 displacer nodes) from cindy_v6 reduced the file dramatically. In the new approach, the X3D file carries geometry only. Displacement data lives in a separate JSON file loaded at runtime.

**What we know works (confirmed today):**
- `_scene.getNamedNode('TestCoord')` ✅
- SAI property writes accepted ✅
- Readback confirms values stick ✅
- Joint rotation via ROUTE fires ✅

**What is NOT YET confirmed:**
- Writing to `Coordinate.point` via SAI actually updates the rendered mesh

---

## Start Day 31 Here

### Priority 1 — Confirm SAI coordinate write moves the mesh (5 minute test)

In the test harness, add a button: "Test Coord Write"

```javascript
window.testCoordWrite = function() {
  var coord = _scene.getNamedNode('TestCoord');
  // Move center vertex (index 4) up 0.3m in Y
  var pts = coord.point;
  pts[4] = new X3D.SFVec3f(0, 0.3, 0);
  coord.point = pts;
  log('Coord write attempted', 'log-ok');
};
```

**If center vertex moves:** SAI coordinate write works. Proceed to Priority 2.
**If center vertex does not move:** Investigate whether `Coordinate.point` is writable via SAI in X_ITE. May need `coord.point = new X3D.MFVec3f(...)` with full array reconstruction.

### Priority 2 — Wire face tab sliders to SAI morph driver

The face tab sliders already exist in the HAnim Editor. Body movements work. The face tab just needs a new backend handler in `mccf_api.py` that:
1. Receives AU name + weight from slider
2. Looks up displacement data from JSON
3. Calls SAI coordinate write on the face mesh

No rebuild of the editor needed. Sliders are fine. Display infrastructure is fine.

### Priority 3 — Build AU displacement data for Cindy's face

One-time bootstrap: define per-vertex displacements for each AU against Cindy's face mesh. This can be done interactively using the face tab sliders in a "paint mode" — move vertices for one AU, save, move to next AU.

The ManyClocks displacement data can be used as a reference for AU shapes, remapped to Cindy's vertex indices.

### Priority 4 — Expression library and lerp

**Format: XML, not JSON.** Displacement data lives in a single XML file that slots into the existing cultivar export pipeline. No new format, no new parser. `mccf_api.py` reads and writes the same XML it already handles.

**Structure:**
```xml
<MCCFExpressions version="1.0">
  <!-- AU displacement geometry — defined once per mesh -->
  <AU name="JawDrop">
    <Displacement coordIndex="4 7 12 15"
                  vectors="0 -0.03 0  0 -0.02 0  0 -0.025 0  0 -0.01 0"/>
  </AU>
  <AU name="LipCornerPull">
    <Displacement coordIndex="22 31"
                  vectors="0.02 0.01 0  -0.02 0.01 0"/>
  </AU>

  <!-- Named expressions — AU weight vectors authored via face tab sliders -->
  <Expression name="content">
    <Weight au="LipCornerPull" value="0.6"/>
    <Weight au="BrowRaise" value="0.2"/>
  </Expression>
  <Expression name="frustrated">
    <Weight au="BrowLowerer" value="0.7"/>
    <Weight au="LipPress" value="0.4"/>
  </Expression>
</MCCFExpressions>
```

**Two sections, one file:**
- `<AU>` blocks: per-vertex displacement geometry for each action unit. Defined once, tied to Cindy's mesh vertex indices. Authored interactively via face tab.
- `<Expression>` blocks: named emotion states as AU weight vectors. Authored via face tab sliders — dial in the look, save with a name. Referenced by cultivar XML at runtime.

**Runtime flow:**
1. Flask loads `cindy_expressions.xml` at startup
2. ϕ/ϵ maps emotional state to expression name
3. Expression name → AU weight vector lookup
4. SAI morph driver applies weights to `Coordinate.point`
5. Lerp between current and target weight vectors for smooth transitions

**Cultivar XML reference:**
```xml
<ExpressionState current="content" target="curious" lerp="0.3"/>
```

Once AU weights drive the mesh:
- Author emotion expressions as AU weight vectors using the face tab sliders
- Save named expressions to JSON: `{ "content": { "JawDrop": 0.1, "LipCornerPull": 0.6, ... } }`
- At runtime, ϕ/ϵ maps to emotion name → AU weight vector
- Lerp between current and target AU weights for smooth transitions

---

## Architecture Invariants (updated Day 30)

All Day 29 invariants hold, plus:

**X_ITE file requirements (ALL required for HAnim geometry to render and animate):**
- `profile='Interchange' version='4.1'` — not Full, not Immersive
- `<component name='HAnim' level='1'/>`
- `<component name='Interpolation' level='1'/>` — WITHOUT THIS, TimeSensor ROUTEs do not fire
- `<component name='EnvironmentalSensor' level='1'/>` — from Cindy's working file
- `loa='4'` on HAnimHumanoid — loa='1' renders nothing
- `containerField='skeleton'` on root HAnimJoint
- `TextureCoordinate` present in every IndexedFaceSet
- Segment-level `<Coordinate DEF='...' containerField='coord'/>` at HAnimSegment scope
- Shape IFS references coord via `<Coordinate USE='...'/>`
- No DOCTYPE declaration
- No xsd: attributes
- ROUTEs last in Scene

**HAnimDisplacer status:** Nodes parse and accept SAI weight writes. Deformation does not fire. Do not use. Use SAI coordinate writes instead.

**SAI initialization pattern (from mccf_api.py):**
- `import X3D from 'https://cdn.jsdelivr.net/npm/x_ite@10.5.2/dist/x_ite.min.mjs'`
- `<script type="module">`
- `X3D.getBrowser(canvas)` — static call on imported module
- Called inside `canvas.addEventListener('load', ...)` 
- Direct property assignment: `node.field = value` not `getField().setValue()`

---

## Files

| File | Status | Notes |
|------|--------|-------|
| `static/test/displacer_test_minimal.x3d` | ✅ Day 30 | Minimal HAnim test, all required structure confirmed |
| `static/test/displacer_test_harness.html` | ✅ Day 30 | SAI test panel — paste from local disk Day 31 |
| `cindy_hanim.x3d` | ✅ Clean baseline | Pre-displacer, Walk/Pivot/Idle confirmed working |
| `cindy_v6_hanim.x3d` | ⚠️ Abandoned | Face transplant + displacer approach abandoned |

---

## Reference Documents (upload at session start)

- `MCCF_HAnim_Editor_Spec.md`
- `MCCF_HAnim_Behavior_Activation_Spec.md`
- `mccf_api.py` — paste from local disk
- `cindy_hanim.x3d` — clean baseline
- `static/test/displacer_test_minimal.x3d` — current test file
- `static/test/displacer_test_harness.html` — current harness
- `ManyClocks.x3d` — AU displacement reference data
