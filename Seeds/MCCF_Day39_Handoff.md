# MCCF Day 39 Session Handoff

**Rule:** Author does not edit code. Claude delivers complete files only.  
**GitHub:** Always one session behind — use uploaded files, not GitHub.

---

## Working File State (End of Day 39)

| File | Lines | Status |
|------|-------|--------|
| `mccf_api.py` | 5536+ | Includes inject-behaviors (harmless), save-face-morph, inject-face-aus, get-face-morph-status, getCoordPositions SAI handler |
| `mccf_character_creator.html` | 4232 | Includes 🎭 behaviors button, face AU capture section in FACE tab |
| `jack_hanim.x3d` | — | `final_low_poly_character__rigged.x3d` — clean, ingested, sliders working |

**Jack cultivar:** ingested, joint_map present, identity WireInterps, SAI round-trip working, sliders confirmed working.

---

## Day 39 Accomplished

### ✅ Face AU capture pipeline built (untested)

**3 new API endpoints:**

`POST /hanim/save-face-morph`  
Body: `{ cultivar, region, pose, coord_def, points:[x,y,z,...] }`  
Stores captured vertex positions in cultivar XML under `<FaceMorphs><Region><Pose>`.  
Pose is `'rest'` or `'morph'`.

`POST /hanim/get-face-morph-status`  
Body: `{ cultivar }`  
Returns which regions have rest/morph captured. Drives the UI status grid.

`POST /hanim/inject-face-aus`  
Body: `{ hanim_src, cultivar }`  
Reads FaceMorphs from cultivar, writes `CoordinateInterpolator DEF="AnimationAdapter_{region}"` nodes + ROUTEs into X3D. Idempotent.

**SAI extension in preview page:**  
`getCoordPositions` message handler — reads live vertex positions from any named Coordinate node, posts `coordPositions` response back to editor. Same pattern as existing `getJointRotation` round-trip.

**Face tab UI:**  
"morph target capture" section with:
- Status grid (8 regions × rest/morph — green ● = captured, grey ○ = missing)
- Region selector dropdown
- `capture rest` / `capture morph` / `inject AUs →` buttons
- Auto-polls status when FACE tab opens

---

## P0 First Thing Next Session — Fix avatar_preview f-string (15 min)

The `avatar_preview` function in `mccf_api.py` returns a large HTML/JS block built as a Python f-string. Every `{` and `}` in the JavaScript — including in comments — must be doubled (`{{` / `}}`). We've been hit by this repeatedly and will keep being hit every time new JS is added to that block.

**Fix:** Convert `avatar_preview` from an f-string to a plain triple-quoted string, then use explicit `.replace()` calls for the small number of Python variables that actually need injection. JavaScript braces can then be written normally.

**Variables currently injected into the template (find with `{[a-z]` pattern):**
- `{src}` — the X3D source path
- `{avatar_name}` — derived from filename
- `{expressions_url}` — path to expressions XML
- Any others found by scanning for single `{` not followed by `{`

**Pattern to use instead:**
```python
html = """...(all JS with normal braces)..."""
html = html.replace('__SRC__', src)
html = html.replace('__AVATAR_NAME__', avatar_name)
# etc.
```

Do this before any other work in the session — it unblocks all future JS additions to the preview page.

---

## Day 39 Testing Sequence

### Step 0 — Deploy and verify base state
1. Deploy `mccf_api.py` and `mccf_character_creator.html` to server, restart Flask
2. Open HAnim Editor → Jack cultivar
3. Confirm sliders still working (regression check)
4. Open FACE tab — confirm "morph target capture" section appears

### Step 1 — Confirm JackCoord nodes exist
Run `POST /hanim/fix-face-coords` with `{ hanim_src: "final_low_poly_character__rigged.x3d" }`.  
Check response `fixed` count — if > 0, nodes were found and fixed.  
**If fixed = 0:** JackCoord nodes may not exist in this file. See "If no JackCoord nodes" below.

### Step 2 — Test getCoordPositions SAI round-trip
In browser console (with Jack loaded in preview):
```js
// Send SAI message manually to test the new handler
document.getElementById('he-xite-frame').contentWindow.postMessage(
  { type: 'getCoordPositions', coordDef: 'JackCoord_skull', region: 'skull' }, '*'
);
// Then listen: window.addEventListener('message', e => console.log(e.data))
// Expect: { type:'coordPositions', region:'skull', found:true/false, points:[...] }
```
If `found: false` — the coord node DEF doesn't match. Check what DEF names actually exist in the X3D with `grep "Coordinate DEF" final_low_poly_character__rigged.x3d`.

### Step 3 — Capture workflow (if coords found)
1. Reset avatar to neutral rest pose
2. FACE tab → select region `skull` → click **capture rest**
3. Confirm toast: "✓ skull rest captured (N pts)"
4. Confirm grid shows green ● for skull rest
5. Use jaw slider slightly (open mouth) → select `jaw` → **capture morph**
6. Reset → **capture rest** for jaw
7. Click **inject AUs →**
8. Confirm toast lists injected regions
9. Move jaw AU slider — verify geometry deformation

---

## If No JackCoord Nodes Exist

The current `final_low_poly_character__rigged.x3d` may not have face region Coordinate nodes at all — the original file was a full-body low-poly export without separate face mesh regions.

**If this is the case, two options:**

**Option A — Simple procedural morphs (recommended for speed):**  
Build a new API endpoint `POST /hanim/generate-face-morphs` that:
1. Reads the avatar's skinCoord (the main `Coordinate DEF="_3"` node) 
2. Identifies face-region vertices by Y-height and Z-depth bounding box (head is above Y=4.5 on Jack's scale)
3. Creates `JackCoord_{region}` nodes by extracting those vertices
4. Generates simple morph targets procedurally (jaw = translate Y down, eyebrows = translate Y up, eyelids = translate Z forward, eyeballs = translate XZ)
5. Injects everything in one pass

**Option B — Use Cindy's morph targets scaled to Jack:**  
Extract Cindy's `CindyCoord_{region}` rest positions, compute per-vertex displacement vectors, scale to Jack's coordinate space, apply to Jack's head vertices. Approximate but fast.

---

## Architecture Reference

### FaceController (already in Jack's X3D)
```
Script DEF="FaceController" directOutput="true"
  au_name(value)   → _au = value
  au_weight(value) → AnimationAdapter_{_au}.set_fraction = value * 0.5
```
When AU slider moves: sends `au_name` then `au_weight` via SAI → FaceController → AnimationAdapter.set_fraction → CoordinateInterpolator interpolates → JackCoord_{region}.point updates → mesh deforms.

### AnimationAdapter node structure
```xml
<CoordinateInterpolator DEF="AnimationAdapter_jaw"
  key="0 1"
  keyValue="{rest_vertex_positions} {morph_vertex_positions}" />
<ROUTE fromNode="AnimationAdapter_jaw" fromField="value_changed"
       toNode="JackCoord_jaw" toField="point" />
```

### Cultivar FaceMorphs XML structure
```xml
<FaceMorphs>
  <Region name="jaw" coord_def="JackCoord_jaw">
    <Pose name="rest"  points="x y z x y z ..." />
    <Pose name="morph" points="x y z x y z ..." />
  </Region>
</FaceMorphs>
```

---

## Deferred Items

| Item | Status |
|------|--------|
| Behavior animations | Deferred — coordinate space mismatch (GLTF vs HAnim 2.0) + ROUTE conflict with WireInterps |
| Viewpoint mismatch | Jack feet at origin vs other avatars body-centered |
| Emotion engine → AU hookup | Blocked on working AUs |

---

## Strategic Context

Author has ~12+ main characters planned for a novel. Avatar pipeline decision pending:
- **Blender route:** learn body construction + rigging + shape keys → GLTF morph targets → auto-extracted by ingest pipeline. Best long-term but time investment.
- **Commercial add-in (Character Creator for Blender):** better skinning quality, still needs bone name mapping in ingest. Purchase decision pending.
- **Current approach:** simple slider-pose capture for face morphs — functional, replaceable later.

Once face AUs work, next major milestone is **emotion engine → AU/joint hookup** to drive expressions from narrative events.

---

## File Locations (this session outputs)
- API: output from Day 39 session (5536+ lines)
- HTML: output from Day 39 session (4232 lines)
- Jack X3D: `static/avatars/final_low_poly_character__rigged.x3d` (on disk, not re-uploaded)
- Cindy reference: `/mnt/user-data/uploads/1780587732094_cindy_hanim.x3d`
- Day 38 Handoff: `/mnt/user-data/uploads/` (previous session)
