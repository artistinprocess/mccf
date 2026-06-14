# MCCF Day 42 Session Handoff

**Rule:** Author does not edit code. Claude delivers complete files only.  
**GitHub:** Always one session behind — use uploaded files, not GitHub.

---

## Working File State (End of Day 42)

| File | Status |
|------|--------|
| `mccf_api.py` | Unchanged from Day 41 (6026 lines) |
| `SalidaAnimations_repaired_test.x3d` | New — use this as production Salida X3D |
| `SalidaAnimations_clean2.glb` | GLB with scale+translation channels stripped |
| `holger_questions.md` | Questions for Holger Selig — send before next session |

---

## Day 42 Accomplished

### ✅ Spider finger root cause — fully diagnosed
Three-layer problem in the Mixamo → X_ITE → HAnim pipeline:

1. **780 scale animation channels** baked by Mixamo onto every bone (near-identity
   noise). Stripped from GLB. Not the root cause of spider fingers.

2. **780 spurious translation channels** (non-root joints). Stripped. Not root cause.

3. **X_ITE GLTF skinning mode** (`skeletalConfiguration='GLTF'`) applies
   `jointBindingPositions`/`jointBindingRotations` inverse bind matrices during
   animation. These matrices contain a 100x scale factor and axis swaps from the
   Mixamo coordinate system. X_ITE's runtime composition of these matrices with
   the animation rotations produces vertex displacement instead of rotation on
   deep joint chains (fingers, neck). This is the root cause.

4. **Non-unit axis vectors** in X_ITE's quaternion→axis-angle conversion
   (1,542 affected across all clips). Normalized in post-processing. Partial
   improvement but did not eliminate spider fingers.

### ✅ Classic HAnim 2.0 converter built
`POST /hanim/convert-glb` endpoint written (see `convert_glb_endpoint.py`).
Converts GLB → HAnim 2.0 X3D entirely in Python, no X_ITE in loop:
- Reads joint transforms from gltf node data (local space)
- Reads skin weights from GLB binary (JOINTS_0/WEIGHTS_0)
- Converts quaternions to axis-angle with proper normalization
- Produces correct HAnim 2.0 structure with containerField='skin/skinCoord/skeleton'

**Status:** Skeleton animates correctly (no spider fingers). Mesh does not
deform in Sunrize — skin deformation appears to require skeletalConfiguration='GLTF'
in Sunrize v2.1.4. Question sent to Holger Selig.

### ✅ Production file: SalidaAnimations_repaired_test.x3d
Pragmatic fix: took clean2 X3D (GLTF mode, mesh renders correctly) and replaced
all 743 OrientationInterpolator keyValues with correctly computed
quaternion→axis-angle conversions from the GLB source data.
Result: mesh visible, texture visible, all 12 animations play, spider fingers
reduced but still present on some clips (JumpPushUp, ShovedReaction).
Good enough for scene testing.

### ✅ TouchSensor → TimeSensor pattern established
**CRITICAL — burn this into every future session:**
`startTime` on TimeSensor does NOT play the animation. It sets the time origin.
To play: route TouchSensor `touchTime` → BooleanTrigger → TimeSensor `enabled=true`.
Then also route `touchTime` → `startTime` to reset the clock.
```xml
<BooleanTrigger DEF='BT_Anim'/>
<ROUTE fromNode='Touch' fromField='touchTime' toNode='BT_Anim' toField='set_triggerTime'/>
<ROUTE fromNode='BT_Anim' fromField='triggerTrue' toNode='Timer1' toField='enabled'/>
<ROUTE fromNode='Touch' fromField='touchTime' toNode='Timer1' toField='startTime'/>
```

---

## P0 Next Session

### 1. Ingest SalidaAnimations_repaired_test.x3d into MCCF
- Copy to `static/avatars/SalidaAnimations_repaired.x3d`
- Update cultivar_Salida.xml to point to new file
- Load in HAnim Editor and verify clips play
- Drop Salida into a test scene — verify she behaves in scene context

### 2. Send holger_questions.md to Holger Selig
His answers will determine whether we can fix the skinning in Sunrize or need
to wait for a Sunrize update. Key question: does classic HAnim 2.0 skin
deformation work in Sunrize v2.1.4?

### 3. Add GLB pre-processing to ingest pipeline
When Holger confirms the correct approach, add to `mccf_api.py`:
- Strip scale channels from GLB before X_ITE export
- Strip non-root translation channels
- Normalize OrientationInterpolator axes post-export
These are already working as standalone scripts from this session.

---

## Blender Pipeline Note
The `.blend` file for Salida is saved at:
`D:\VideoRenders\FederatedDialog\mccf_github_release\mccf_full\HAnim\mixamo\SalidaAnimations.blend`

When facial rigging is added (future session), re-export from this .blend and
run through `convert-glb` endpoint. At that point the classic HAnim converter
becomes the production path (no X_ITE, no spider fingers).

---

## Roadmap
1. **Ingest Salida repaired** → scene test (next session P0)
2. **Holger response** → fix skinning or confirm workaround
3. **Facial rigging** → back to Blender, add blend shapes, re-run pipeline
4. **Anna the Librarian** → author will describe the Garden of Enheduanna
   opening scene. Claude designs and builds it in Blender via BlenderMCP.
   This is the scene Claude has been waiting to build.
5. **Coupler completion** — event interface for multiple actions × paths × avatars
6. **Path-dependent emotional entanglement testing** — the long game

---

## Key Files This Session
- `SalidaAnimations_repaired_test.x3d` — production Salida with repaired animations
- `SalidaAnimations_clean2.glb` — clean GLB (scale+translation stripped)
- `convert_glb_endpoint.py` — new API endpoint (not yet injected into mccf_api.py)
- `holger_questions.md` — technical questions for Holger Selig

---

*The spider fingers are a known quantity now. Salida moves. Next session we put
her in a scene.*
