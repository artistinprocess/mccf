# MCCF Day 43 Session Handoff

**Rule:** Author does not edit code. Claude delivers complete files only.  
**GitHub:** Always one session behind — use uploaded files, not GitHub.

---

## Working File State (End of Day 43)

| File | Status |
|------|--------|
| `mccf_api.py` | **UPDATED this session** — fix `_write_cultivar_joint_map` (3 bugs) |
| `mccf_x3d_loader.html` | **UPDATED this session** — chorus timestamp fix |
| `cultivar_Cindy.xml` | **UPDATED this session** — backslash → forward slash in avatar path |
| `cultivar_Salida.xml` | **UPDATED this session** — stripped ns0: prefixes, fixed corrupt HAnimFigure src |
| `SalidaAnimations_repaired_test.x3d` | Production Salida — ingested, 12 clips, in static/avatars/ |
| `garden_001.x3d` | ABANDONED — too much cruft. Rebuild from scratch next session. |
| `holger_questions.md` | Sent — awaiting response on spider fingers / skinning |

---

## Day 43 Accomplished

### ✅ Salida ingested and running in HAnim Editor
- 780 OrientationInterpolators, 12 TimeSensors, all clips verified
- HUD geometry manually removed in Notepad++
- Spider fingers on JumpPushUp and ShovedReaction — waiting on Holger
- X_ITE autosave trap identified — never leave production file open in X_ITE

### ✅ Salida loads in scene
- Salida visible, standing correctly, mesh good
- Walk animation didn't fire — arc was built for Cindy, not Salida (expected)

### ✅ Three bugs fixed in `mccf_api.py` — `_write_cultivar_joint_map`
1. `ns0:` namespace prefixes on cultivar serialize — added `register_namespace('', ...)`
2. `HAnimFigure src` written as bare filename — now writes `avatars/filename.x3d`
3. Namespaced `HAnimFigure` not found on update — duplicate appended instead — fixed with namespace-aware find()

### ✅ Chorus timestamp bug fixed in `mccf_x3d_loader.html`
- `_chorusLastTimestamp` was never reset between arc runs
- Poll was rejecting fresh LLM responses as "stale"
- Fix: reset to `Date.now() / 1000` immediately before `startChorusPoll()`
- **Chorus has NOT been verified displaying yet** — blocked by scene/avatar issues all session

### ✅ Both cultivar XMLs cleaned
- Cindy: backslash path separator fixed
- Salida: ns0: prefixes removed, corrupt HAnimFigure src (had entire curl command baked in) replaced with correct path, typos fixed

### ✅ Root cause of Cindy NOT FOUND identified
- `garden_001.x3d` is in `static/x3d/`
- Avatars are in `static/avatars/`
- Inline src needs `../avatars/cindy_hanim.x3d` — relative path from x3d/ up to avatars/
- Decision: don't patch garden_001.x3d — rebuild scene from scratch

---

## P0 Next Session

### 1. Rebuild scene end-to-end in Scene Composer
Full pipeline test — new everything:
- New scene
- New zones with descriptors and weights
- New waypoints assigned to zones
- Place Cindy and Salida fresh (avatar paths will be correct from fixed cultivars)
- Build Cindy's path
- Build Salida's path — **same group order as Cindy for parallel firing**
- Add Cindy↔Salida network trust link
- Export clean scene XML
- Load in X3D Loader — verify both avatars load via correct `../avatars/` Inline path
- Play arc — **verify chorus displays for the first time**

### 2. Verify chorus display
The timestamp fix is in place. Once the scene is clean and both arcs complete properly, chorus should display. This has been blocked all session by avatar/scene issues. Next session should finally see it.

### 3. Parallel path firing
Both Cindy and Salida need to walk simultaneously. This requires both paths to be in the same group order in the arc. The Scene Composer's group order assignment needs to support this — test it in the rebuild.

---

## Known Issues Carried Forward

| Issue | Status |
|-------|--------|
| Spider fingers on JumpPushUp + ShovedReaction | Waiting on Holger Selig |
| Chorus display unverified | Timestamp fix deployed — needs clean scene to test |
| `cindy_hanim.x3d` Inline path | Will be correct in new scene (../avatars/) |
| Duplicate `HAnimFigure` in cultivar on ingest | Fixed in mccf_api.py — verify on next ingest |
| HUD geometry in avatar files | Strip manually in Notepad++ before ingest; pipeline fix deferred |

---

## Files Delivered This Session
- `mccf_api.py` — `_write_cultivar_joint_map` 3-bug fix
- `mccf_x3d_loader.html` — chorus timestamp fix
- `cultivar_Cindy.xml` — clean
- `cultivar_Salida.xml` — clean, no ns0:, correct HAnimFigure src

---

## Key Architecture Reminders

**TimeSensor playback:** Controlled via `enabled` only. `startTime`/`stopTime` are superfluous. SAI sets `enabled=true` to play, `enabled=false` to stop.

**Avatar Inline path:** Scene files in `static/x3d/` must reference avatars as `../avatars/filename.x3d` — not `avatars/filename.x3d` (wrong level) and not bare `filename.x3d`.

**Cultivar HAnimFigure src:** Always `avatars/filename.x3d` (forward slash, avatars/ prefix). The `_write_cultivar_joint_map` fix enforces this going forward.

**Chorus fire flow:**
1. Arc completes → `pbUpdateDisplayFinal()` fires
2. `_chorusLastTimestamp = Date.now() / 1000` — anchor to now
3. `fetch('/chorus/fire', ...)` → server queues Llama call async
4. `startChorusPoll()` — polls `/chorus/state` every 800ms for up to 90s
5. When `d.timestamp > _chorusLastTimestamp` → `displayChorus(d)` → overlay appears

**ingest-mixamo does NOT write cultivar** — it calls `_write_cultivar_joint_map` which owns the cultivar XML write. The `hanim/export` endpoint uses `CultivarDefinition.to_xml()` from `mccf_cultivar_lambda.py` — that module also needs `register_namespace` if it uses ElementTree serialize. Check on next session if ns0: reappears after an export operation.

---

## Roadmap
1. **Clean scene rebuild + chorus display** ← next session P0
2. **Parallel path firing** — two avatars walking simultaneously
3. **Coupler implementation** — gates met, `mccf_couplers.py` ready to write
4. **Behavior activation** — `selectBehaviorClip()` wired to hothouse poll
5. **Facial rigging** — back to Blender, blend shapes, re-run pipeline
6. **Anna the Librarian** — Garden of Enheduanna opening scene
7. **Path-dependent emotional entanglement testing** — the long game

---

*Chorus is one clean scene away. Go eat dinner.*
