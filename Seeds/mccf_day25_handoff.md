# MCCF Day 25 Session Handoff
**Generated:** 2026-05-23 ~19:17 UTC (end of Day 24 / start of Day 25)
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## Where We Are Right Now

Scene `garden_001` runs end-to-end. Cindy HAnim figure is visible in scene, moves along path, TTS fires, Chorus fires, Gardener cylinder placeholder works. The **one remaining blocker** is behavior timer mapping — Cindy loads in Kick pose instead of idle stand, and animations do not run during playback.

### Final fix deployed (not yet tested)
`mccf_x3d_loader.html` — last file in outputs. `tryMapTimers` now uses **`getImportedNode` only** — no `addImportedNode`. This is the correct fix based on Day 24 diagnostics (see below).

**Start Day 25 by asking for the console output of this loader.** The expected success signal is:
```
pbActivateX3DTimers: behavior timers mapped for Cindy (attempt N) — DefaultTimer, PitchTimer, YawTimer, RollTimer, WalkTimer, RunTimer, JumpTimer, KickTimer
pbActivateX3DTimers: DefaultTimer started for Cindy
```

---

## Day 24 Key Discoveries (Chronological)

### 1. X_ITE IMPORT/EXPORT — what actually works
The **declarative `<IMPORT>` statements in the X3D scene file ARE processed** by X_ITE. They register imported node names (e.g. `DefaultTimer_Cindy`) into the parent scene's imported node table at parse time.

**`getNamedNode` does NOT resolve IMPORT'd nodes** — this was the Day 23 blocker.

**Holger Seelig (X_ITE author) confirmed** the correct SAI path:
- `X3DExecutionContext.addImportedNode(inlineNode, exportedName, importedName)` — programmatic registration
- `X3DExecutionContext.getImportedNode(importedName)` — retrieval
- Refs: https://create3000.github.io/x_ite/reference/scene-services/#addimportednode-inlinenode-sfnode-exportedname-string-importedname-string-void

**Day 24 diagnostic revealed:** `addImportedNode` throws `"imported name 'DefaultTimer_Cindy' already in use"` — because the `<IMPORT>` declarative statement already registered it. So `addImportedNode` is NOT needed.

**Current approach:** `getImportedNode` only, with 20-retry × 250ms loop. The node names are registered immediately at parse, but resolve to null until the Inline finishes loading the HAnim file. The retry loop waits for resolution.

**`loadState` property** — tried as a load-complete signal. Returns `undefined` in current X_ITE version. Not usable.

### 2. Option C (inline HAnim XML) — attempted and permanently abandoned
Tried fetching stripped HAnim XML and inlining it directly into the scene graph. Problems:
- Nested `<X3D>` wrapper crash (fixed)
- HAnim HAnimHumanoid USE/DEF forward-reference errors when inlined into parent Transform
- Avatar invisible

**Decision: Option C is dead. Inline + IMPORT is the correct architecture.**

### 3. Scene Composer reverted to sync
After Option C attempt, `buildAX3D`, `buildX3DString`, `exportX3D`, and `sendToLauncher` were all made async. **All reverted to sync** in Day 24. Scene Composer is now clean.

### 4. Jin.png texture fix
`cindy_hanim.x3d` had hardcoded Windows local path in `ImageTexture DEF="JinLOA4TextureAtlas"`:
```
url="C:\Users\PCAudioLabs\Downloads\images\Jin.png", "https://www.web3d.org/x3d/content/examples/HumanoidAnimation/Characters/images/Jin.png"
```
**Fixed to:** `url='"Jin.png"'` (relative — resolves from `static/avatars/`)

`Jin.png` must be present at `static/avatars/Jin.png`. Fetched from W3DC by author.

---

## Current File State

| File | Location | Status | Notes |
|------|----------|--------|-------|
| `mccf_x3d_loader.html` | `static/` | ⚠️ **DEPLOY + TEST** | `getImportedNode`-only fix, not yet confirmed |
| `mccf_scene_composer.html` | `static/` | ✅ Deployed | Sync, Inline + IMPORT, no Option C |
| `cindy_hanim.x3d` | `static/avatars/` | ✅ Deployed | Jin.png relative path fixed |
| `Jin.png` | `static/avatars/` | ✅ Deployed | Fetched from W3DC by author |
| `garden_001.x3d` | `static/x3d/` | ✅ Re-exported | Clean Inline + IMPORT, no Option C content |

---

## Architecture Invariants (unchanged)

- `waypointOrder` (SFInt32, initializeOnly) — REQUIRED on every Path node
- ROUTEs MUST be last in X3D scene file
- All Timers/Dwells: `enabled="false"` in X3D file
- `var API = 'http://localhost:5000'` in both HTML files
- Behavior timer DEF convention in HAnim file: `DefaultTimer`, `PitchTimer`, `YawTimer`, `RollTimer`, `WalkTimer`, `RunTimer`, `JumpTimer`, `KickTimer`
- IMPORT AS convention in scene: `TimerBase_AgentSafeName` (e.g. `DefaultTimer_Cindy`)
- HAnim Inline DEF convention: `HAnim_AgentSafeName` (e.g. `HAnim_Cindy`)
- HAnim files: `static/avatars/` — EXPORT statements required for all 8 timer bases
- Cultivar files: `cultivars/cultivar_*.xml`
- Arc files: `exports/` — bare filename, no path prefix

---

## Known Non-Issues (do not fix)

- `ambient/sync 500` — mccf_lighting module missing, not in scope
- `lighting/scalars 404` — same
- AudioContext gesture warning — browser policy, harmless
- `HAnimHumanoid.segments deprecated` — X3D 4.x cosmetic warning, X_ITE still honors it
- Tracking Prevention blocked jsdelivr storage — Edge/Firefox cookie policy, harmless

---

## After Behavior Timers Confirmed Working

Next work items in order:

1. **Fix initial pose** — Cindy loads in Kick pose. Once DefaultTimer fires on load this should resolve. If not, check HAnim file's default animation state.

2. **Add Anna** — second HAnim agent. Path waypointOrder TBD. Final waypoint monologue ends with "They are our incense." / "Blessed be."

3. **Rename scene** — `garden_001` → `hypoborea_001` after Anna is working.

4. **W3C/X_ITE bug reports** (low priority, send to Holger):
   - `namedNodes` returns numeric array not name-keyed map (X3D spec violation)
   - `loadState` not exposed on Inline nodes (X3DUrlObject spec violation)

---

## Console Diagnostic Reference

**Success (what we're looking for):**
```
pbActivateX3DTimers: behavior timers mapped for Cindy (attempt N) — DefaultTimer, PitchTimer...
pbActivateX3DTimers: DefaultTimer started for Cindy
```

**If still failing after 20 retries:**
- Check `cindy_hanim.x3d` EXPORT statements are present (8 of them, at end of file)
- Check `garden_001.x3d` IMPORT statements are present (8 of them, AS DefaultTimer_Cindy etc.)
- Verify `getImportedNode('DefaultTimer_Cindy')` returns non-null in browser console:
  ```javascript
  canvas.browser.currentScene.getImportedNode('DefaultTimer_Cindy')
  ```
  Run this after scene loads but before Play. If null, Inline hasn't resolved yet. If throws, name not registered — check IMPORT statements in scene.
