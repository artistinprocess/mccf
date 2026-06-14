# MCCF Day 40 Session Handoff

**Rule:** Author does not edit code. Claude delivers complete files only.  
**GitHub:** Always one session behind — use uploaded files, not GitHub.

---

## Working File State (End of Day 40)

| File | Lines | Status |
|------|-------|--------|
| `mccf_api.py` | 5940 | Mixamo ingest pipeline complete and working |
| `mccf_character_creator.html` | 4299 | heLoadJoints extracted; ingest mixamo button working |
| `final_low_poly_character__rigged.x3d` | — | Jack — unchanged |
| `mixamo1.x3d` | — | Salida — must be fresh copy before re-ingest |

**Salida cultivar:** Points to `mixamo1.x3d`. Joint map written. Timer1 at Scene root, `loop="true" enabled="false"`. Animation plays and loops via play button. Pose sliders work and stop animation. Play button restores animation.

**Cindy cultivar:** Confirmed working — behaviors (Run, Walk, etc.) loop correctly after Day 40 fixes.

---

## Day 40 Accomplished

### ✅ Mixamo ingest pipeline — fully working

`POST /hanim/ingest-mixamo` now produces a correct X3D:

1. **Scripting component** added to `<head>` so FaceController export works later
2. **Timer1 moved to Scene root** — X_ITE's `getNamedNode` only searches Scene root namespace, not nested groups. Mixamo puts Timer1 inside `Group[Animations]>Group[mixamo-com]`.
3. **`loop="true" enabled="false"` set on Timer1** — Mixamo exports neither attribute; X_ITE defaults `loop=false` which causes single-play. `enabled=false` means it waits for the play button rather than auto-playing on load.
4. **EXPORT nodes removed** — Three `<EXPORT localDEF="..."/>` nodes at Scene level re-exported the nested Timer1 back into the namespace, overriding the moved one. Ingest removes them.
5. **WireInterp DEFs sanitised** — Colons in `mixamorig:Hips` are illegal in XML NCNames. All WireTimer/WireInterp DEFs replace `:` and `-` with `_`.
6. **Joint tree shows HAnim names** — `/hanim/joints` applies joint_map before returning. Tree shows `r_shoulder`, `l_hip` etc. `_joint_region()` extended for `mixamorig:*` names.
7. **`heLoadJoints()` extracted** — Was inline in `hePoseInit`. Now a standalone function callable after ingest to refresh the tree without reopening the tab.

### ✅ P0 f-string fix (from Day 39)
`avatar_preview` converted from f-string to plain string + `.replace()`.

### ✅ Cindy regression fixed
`enableTimer` was wrapped in try/catch that swallowed errors before `enabled=true` fired. Stripped back to just `timer.enabled = true` — that's all X_ITE needs.

---

## Known UI Quirk — Ingest Button State

The **⚡ ingest mixamo** button visibility is driven by whether the loaded clips are "raw Mixamo" (timerDEF doesn't end with `_Timer`). After ingest, `Timer1` is still named `Timer1` so the button keeps showing. This is harmless — re-ingesting an already-ingested file is idempotent. 

When switching between avatars (e.g. Cindy → Salida), the button state reflects the last-loaded file until joints are refreshed. Watch for stale state if the editor is loaded with a previously-ingested file — the ingest button may show unnecessarily but clicking it won't break anything.

**Future fix:** Add `wired: true` flag to `/hanim/joints` response when WireInterp nodes are detected, and use that to hide the button definitively.

---

## P0 Next Session — BlenderMCP Setup

The author saw a YouTube video about BlenderMCP — Claude connected directly to Blender via MCP for prompt-driven 3D work. **Set this up before downloading more Mixamo animations** — it will automate the NLA merge workflow for combining multiple clips.

**Requires Claude Desktop app** (not claude.ai web). Install first if not already installed.

**Setup steps:**
1. Install Claude Desktop: https://claude.ai/download
2. Download `addon.py` from https://github.com/ahujasid/blender-mcp
3. In Blender: Edit → Preferences → Add-ons → Install → select `addon.py` → enable "MCP Blender Bridge"
4. In Blender sidebar (N key): BlenderMCP tab → **Start MCP Server**
5. In Claude Desktop: Settings → Developer → Edit Config → add:
```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["blender-mcp"]
    }
  }
}
```
6. Restart Claude Desktop — hammer icon should appear with Blender tools
7. Test: "What objects are in my Blender scene?"

**Once connected, the multi-animation merge workflow is:**
```
"Import mixamo1.fbx as base character. Import walk.fbx, run.fbx, idle.fbx 
as separate NLA actions on the same armature. Export as mixamo1_multiclip.gltf 
with all animations included."
```

---

## P1 — Multiple Mixamo Animation Clips

Each Mixamo animation is a separate FBX download. To get walk/run/idle on Salida:

1. Go to mixamo.com — character rig is remembered
2. Pick animation → Download FBX **without skin** (animation only)
3. Repeat for each clip (walk, run, idle, wave, etc.)
4. Merge in Blender via NLA editor (manual) or BlenderMCP (prompted — much faster)
5. Export GLTF → X_ITE → X3D
6. Copy fresh X3D to `static/avatars/mixamo1.x3d`
7. Run **⚡ ingest mixamo** — each TimeSensor becomes a playback button

---

## P2 — Ingest Button Visibility Fix

After ingest, `Timer1` is still named `Timer1` so the Mixamo detection logic keeps showing the button. Fix:

In `/hanim/joints`, add to response:
```python
'wired': any(
    el.get('DEF','').startswith('WireInterp_')
    for el in root.iter('OrientationInterpolator')
)
```

In `heLoadJoints()` HTML, add:
```javascript
if (mixamoIngestBtn)
  mixamoIngestBtn.style.display = (mixamoRaw && !d.wired) ? '' : 'none';
```

---

## Architecture — Mixamo X3D Structure After Ingest

```
Scene
  Group[Scene0]              ← mesh + HAnim skeleton (unchanged)
  Group[Animations]
    Group[mixamo-com]
      PositionInterpolator × 65   ← translation keyframes
      OrientationInterpolator × 65 ← rotation keyframes  
      ScaleInterpolator × 65      ← scale keyframes
      (Timer1 removed from here)
  TimeSensor[Timer1]         ← MOVED HERE: loop=true, enabled=false
  ROUTE × 390                ← Mixamo animation wiring (unchanged)
  TimeSensor[WireTimer_mixamorig_Hips]  ← pose infrastructure
  OrientationInterpolator[WireInterp_mixamorig_Hips]
  ... × 65 joints
  ROUTE × 780                ← WireInterp pose wiring
  (EXPORT nodes removed)
```

### Pose vs Animation:
- **Animation:** Timer1 `enabled=true` → keyframes drive all bones
- **Pose:** First slider write stops Timer1, WireInterp writes target rotation
- **Back to animation:** Play button sets Timer1 `enabled=true`

### SAI DEF name rule:
`mixamorig:Hips` → `WireInterp_mixamorig_Hips` (colon replaced with underscore)  
Same sanitisation applied in preview page JS before `getNamedNode`.

---

## Deferred Items

| Item | Status |
|------|--------|
| Ingest button stays visible after ingest | Cosmetic — P2 fix above |
| Face AUs for Salida | Blocked — no face coord nodes in Mixamo X3D. Needs BlenderMCP + Day 39 capture pipeline |
| Multiple animation clips for Salida | P1 — needs BlenderMCP NLA merge |
| Behavior animations (Jack) | Deferred — coordinate space mismatch GLTF vs HAnim 2.0 |
| Emotion engine → AU hookup | Blocked on working AUs |
| `XML Parsing Error line 1 col 1` in preview | `_fetchGlobalIndices` tries to parse preview HTML as XML. Harmless/noisy. Fix: check Content-Type before DOMParser call |
| Viewpoint mismatch | Jack feet at origin vs other avatars body-centered |

---

## File Locations
- API: Day 40 session output (5940 lines)
- HTML: Day 40 session output (4299 lines)
- Jack X3D: `static/avatars/final_low_poly_character__rigged.x3d`
- Salida X3D: `static/avatars/mixamo1.x3d` — **restore fresh copy before re-ingest**
- Cindy reference: `static/avatars/cindy_hanim.x3d`
