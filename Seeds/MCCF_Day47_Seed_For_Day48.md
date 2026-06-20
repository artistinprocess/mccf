# MCCF Day 48 Session Seed — Handoff from Day 47

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Needs commit after Day 48 testing confirms green. Last commit `93784f3` on master.
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**

---

## System Status — End of Day 47

**Scene load/save fully working.** Zones, waypoints, paths, agents all restore correctly from XML.
**Sound engine working.** Music fires on Play. Zone ambients wired but trigger not yet confirmed.

- Music (Track 1) — `startTime="-1" stopTime="-2"` guard in X3D; SAI fires on Play only
- Bed (Track 3) — same guard; SAI fires on Play only (no longer left to AudioDestination)
- Zone ambients (Track 2) — `SoundFader_<sid>` Scripts + ROUTE from `Prox_<sid>`
- Stop button calls `spStopAll()` — stops all clips
- Scene composer restores full scene state on load (zones, waypoints, paths, networks, sound)

**GitHub NOT current. Commit after Day 48 test confirms green.**

---

## Working File State

| File | Location | Status |
|------|----------|--------|
| `mccf_x3d_loader.html` | `static/` | Day 47 — Play-gated sound, AudioContext unlock decoupled |
| `mccf_scene_composer.html` | `static/` | Day 47 — Full scene restore, position normalizer, loadAll guard |
| `testScene1.x3d` | `static/x3d/` | Day 47 re-export — AudioDestination guards, SoundFader, ROUTEs |
| `testScene1_scene.xml` | `scenes/` | Day 47 re-export — SceneSound, Zones, Waypoints, Paths |
| `testScene1_zones.xml` | `zones/` | Day 47 export — SoundDesign blocks present |
| `garden_002.x3d` | `static/x3d/` | **Needs re-export** — still uses old Sound nodes (no AudioDestination guards) |
| `garden_002_scene.xml` | `scenes/` | Unchanged |
| `garden_002_zones.xml` | `zones/` | Unchanged |
| `mccf_api.py` | root | Day 45 — `/media/list` endpoint present |
| `mccf_reaper_bridge.py` | root | Untested |

---

## Day 47 Work Completed

### Design Principle Established: Play is Performance

All active objects start with Play except those set by other events (zone triggers, dwell timers).
Applies to Music, Bed, and all future auto-start behavior. Scene load is silent.
Eventually scenes will autoload and run in author-specified order (TBD) — Play is still the
performance gate within a session.

### Sound Gate Fix

**Loader (`mccf_x3d_loader.html`):**
- `_resumeAudioContext`: removed all `spStartSceneTracks()` calls. Now ONLY unlocks AudioContext on first user gesture. Logs "awaiting Play button" in console.
- `spStartSceneTracks`: completely rewritten. Both `Clip_Music` and `Clip_Bed` started via explicit SAI — `stopTime = tNow - 0.01`, `startTime = tNow + 0.05`. Bed no longer left to AudioDestination. Called only from `pbPlay` and `pbPlayAll`.

**Composer (`mccf_scene_composer.html`):**
- `exportX3D` + `buildX3DString`: both `Clip_Music` and `Clip_Bed` now emit `startTime="-1" stopTime="-2"` guard. AudioDestination cannot auto-fire them at scene load.

### Scene Restore Fix

**Root causes found:**
1. `_restoreChorusFromXml` required zones pre-populated by server — they weren't. Silently skipped all zones.
2. Server `/waypoint` returns flat `pos_x`/`pos_z` fields; `drawWP` expects `position:[x,0,z]` array. All waypoints rendered at scene center, hidden under temple zone.
3. `loadAll` async fetch resolved after XML restore and clobbered waypoints/paths with server state.

**Fixes:**
- `_restoreChorusFromXml`: completely rewritten. Builds zones, waypoints, paths unconditionally from raw XML. No pre-existing entries required. Restores: scene name/dimensions, zone geometry + chorus + commands + sound, waypoints with QA lines, paths with waypoint sequences + waypointOrder, network links, scene sound, placed agents. Sets `window._sceneXmlLoaded = true` on completion. Logs `[restore] zones: N waypoints: N paths: N networks: N`.
- `_normalizeWaypointPositions(wps)`: new shared helper. Converts `pos_x`/`pos_z` flat fields to `position:[x,0,z]` array. Called in `_applyLoadedScene` and `loadAll`.
- `loadAll`: guarded with `if (!window._sceneXmlLoaded)` before overwriting zones/waypoints/paths. Still fetches agents and cultivars unconditionally.
- `applyScene` (Apply Grid): clears `window._sceneXmlLoaded = false` for fresh authoring sessions.

### End of Day 47 Test Results

- [x] Music fires on Play button, not on scene load ✅
- [x] Bed fires on Play (Clip_Bed not found on testScene1 — garden_002 not re-exported, expected) ✅
- [x] Stop button stops all audio ✅
- [x] Zones restore on composer scene load ✅
- [x] Waypoints restore and render at correct canvas positions ✅
- [x] Paths restore and render connecting lines ✅
- [x] Full scene loaded → exported → played with sound — green ✅
- [ ] Zone ambient fires on avatar enter — not yet confirmed
- [ ] Dwell sound fires — not yet wired
- [ ] garden_002 re-export — not yet done

---

## X3D Architecture (permanent record — Day 47)

```
Track 1: Music   — scene root, AudioDestination, loop=author-set, gain=author-set
Track 2: Ambient — inside Zone Transform, AudioDestination gain=0, SoundFader activates
Track 3: Bed     — scene root, AudioDestination, loop=author-set, gain=author-set
Track 4: Dwell   — inside Zone Transform, AudioDestination, loop=false, fires on dwell
```

**X3Dv4 Music/Bed pattern (confirmed working, Day 47):**
```xml
<!-- startTime=-1 stopTime=-2: guard against AudioDestination auto-fire at scene load -->
<!-- Loader SAI fires on Play button only. Play is performance. -->
<AudioDestination DEF="SoundNode_Music" gain="0.35">
  <AudioClip DEF="Clip_Music" containerField="children"
      url='"media/OrchestraChorus1.mp3"' loop="false" gain="1.0"
      startTime="-1" stopTime="-2"/>
</AudioDestination>
```

**spStartSceneTracks SAI pattern (loader, Day 47):**
```javascript
clip.stopTime  = tNow - 0.01;  // clear startTime=-1 stopTime=-2 guard
clip.startTime = tNow + 0.05;  // fire ~50ms from now
```

**Key facts (unchanged from Day 46):**
- `AudioClip.gain` is volume (not `Sound.intensity` — Sound node is X3Dv3, ignored by X_ITE 11.6)
- `containerField="children"` required on all AudioClips feeding into AudioDestination
- `SoundFader` sets `dest.gain` on zone enter/exit (AudioDestination.gain, not Sound.intensity)

---

## Known Bugs Carried Forward

| Bug | Where | Notes |
|-----|-------|-------|
| garden_002.x3d uses old Sound nodes | static/x3d/ | Re-export from updated composer. Clip_Bed not found until done. Jack/Cindy/Gardener timer nodes also missing. |
| Zone ambient trigger unconfirmed | loader | ProximitySensor fires on camera/viewer proximity, not avatar. `spZonePoll` polls avatar Translation node — confirm `spTriggerZone` fires `SoundFader_temple.isActive`. Check console for `SoundFader_temple: ENTER`. |
| Dwell sound not wired | loader | `Clip_{safeId}_Dwell` exists in X3D. `pbReleaseDwell` has callback. Wire `startTime` SAI there. |
| `spInit` shows 0 zones | loader | `spDiscoverZones` SAI enumeration races with scene load. Non-blocking — zones work via `spBuildZoneGeometryFromXml`. |
| behavior timers for Salida | loader | `DefaultTimer_Salida` not found — H-Anim not assigned. Expected for cylinder avatar. |
| Jack/Cindy/Gardener timers not found | loader | Only Salida has nodes in testScene1. Expected until garden_002 re-export. |
| `pbPushPosition: no cultivar in wp` | loader | Empty waypoint at end of arc. Minor — does not affect playback. |

---

## Next Session Primary Tasks (Day 48)

### Priority 1 — garden_002 re-export
Re-export `garden_002.x3d` from the updated composer. Verify AudioDestination guards on Music/Bed. Test full garden_002 scene with Jack, Salida, Cindy, Gardener. Confirm Clip_Bed found and fires on Play.

### Priority 2 — Zone ambient trigger confirmation
Run testScene1. Watch console for `SoundFader_temple: ENTER` when Salida arrives at WP2 (temple zone). If not firing: `spZonePoll` fires `spTriggerZone` → should call `SoundFader_temple` `isActive` field via SAI. Trace the path — may need SAI write instead of relying on ProximitySensor ROUTE.

### Priority 3 — Dwell sound wire-up
In `pbReleaseDwell`, after dwell timer fires, add:
```javascript
var dwSafeId = safeId(agentId + '_' + segIdx);  // match composer's SoundFader naming
var dwClip = scene.getNamedNode('Clip_' + dwSafeId + '_Dwell');
if (dwClip) { dwClip.stopTime = tNow - 0.01; dwClip.startTime = tNow + 0.05; }
```

### Priority 4 — Chorus display confirmation
After zone trigger confirmed, verify Chorus overlay appears when avatar enters a zone with Chorus authored.

---

## Bigger Picture (unchanged from Day 45)

1. **Cameras + Lights tab** in loader
2. **Avatar scaling fix** — Salida/Jack mismatch
3. **Pivot/facing direction** — avatars face direction of travel
4. **Character prompt authoring** — Salida brief (200 words)
5. **ElevenLabs + SSML emotion mapping** — gate: sound stable ✓ (Day 46), scene restore stable ✓ (Day 47)
6. **Reaper bridge testing**
7. **Scene player script** — headless playback
8. **User's Guide + System Manual** — sound architecture + scene restore sections

---

## Theoretical Foundations — Filed for Future Reference

### MCCF Coherence Transport Geometry
*Status: Planted flag. Prerequisites: garden_002 tested, ElevenLabs wired, 100+ arc runs, arc schema formalized.*

The seven couplers may be not just dynamics but coordinates — axes of a coherence manifold. The Witness→Steward arc is a path through a space that has shape. Any transport geometry work must preserve the coupler architecture as the explanatory layer. A black-box predictor would compress output without preserving constitutional content.

*Reference: MCCF_FUTURE_TRANSPORT_GEOMETRY.md (generated June 2026, in outputs)*

### BAML Assessment
*Status: Noted. Entry point: dialogue generation (Salida speech) before coupler update functions.*

Typed `.baml` prompt files, version-controlled cultivar prompts, one schema across the multi-LLM ensemble. Alex Hoffman flagged it originally.

### Technē (x3d_mcp) Assessment
*Status: Noted. Applicable when MCCF moves to programmatic scene generation via MCP.*

Craft validation proxy catches missing `containerField`, bad HAnim rigs, etc. `rules.py` catalog immediately useful for MCCF-specific X3D craft rules without adopting the full proxy.

*Reference: https://github.com/EUPHEMEME/x3d_mcp/blob/techne/techne/README.md*

---

## The Reaper Vision (keep visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

---

*GitHub NOT current. Commit after Day 48 test confirms green.*
*Day 47 complete: Play-gated sound + full scene restore working.*
*Day 48 bricks: garden_002 re-export, zone ambient trigger, dwell wire-up.*
