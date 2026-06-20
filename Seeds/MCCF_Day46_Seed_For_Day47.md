# MCCF Day 46 Session Seed — Handoff for Day 47

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Needs commit after Day 47 testing confirms green. Last commit `93784f3` on master.
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**

---

## System Status — End of Day 46

**Sound engine is working.** Session C complete.
- Music (Track 1) plays via `AudioDestination` — `loop=false` restarts via SAI on gesture unlock
- Bed (Track 3) plays via `AudioDestination` — `loop=true` auto-starts on scene load
- Zone ambients (Track 2) wired: `SoundFader_<sid>` Script + ROUTE from `Prox_<sid>` — fires on ProximitySensor `isActive`
- Stop button calls `spStopAll()` — stops all clips
- Sound panel shows Music/Bed filenames from scene XML
- Zone panel populated from scene XML geometry (no hardcoded garden_002 fallback)
- `AudioDestination` replaces `Sound` node throughout — confirmed working in X_ITE 11.6

**Known issue:** Music starts as soon as scene loads (AudioDestination fires at time=0), then restarts correctly on Play. Acceptable for now — gate with Stop if needed.

**GitHub NOT current. Commit after Day 47 test confirms green.**

---

## Working File State

| File | Location | Status |
|------|----------|--------|
| `mccf_x3d_loader.html` | `static/` | Day 46 — Session C complete, sound working |
| `mccf_scene_composer.html` | `static/` | Day 46 — AudioDestination emitter, SoundFader Scripts |
| `testScene1.x3d` | `static/x3d/` | Day 46 export — AudioDestination, SoundFader, ROUTEs |
| `testScene1_scene.xml` | `scenes/` | Day 46 export — SceneSound block present |
| `testScene1_zones.xml` | `zones/` | Day 46 export — SoundDesign blocks present |
| `garden_002.x3d` | `static/x3d/` | Needs re-export from updated composer (still uses old Sound nodes) |
| `garden_002_scene.xml` | `scenes/` | Unchanged |
| `garden_002_zones.xml` | `zones/` | Unchanged |
| `mccf_api.py` | root | Day 45 — `/media/list` endpoint present |
| `mccf_reaper_bridge.py` | root | Untested |

---

## Day 46 Work Completed

### Session C — Sound Engine ✅

**Root cause found and fixed:** X_ITE 11.6 uses X3Dv4 `AudioDestination` node, not the X3Dv3 `Sound` node. `Sound` nodes were silently ignored for Music/Bed. Zone ambients needed same fix.

**Composer changes (`mccf_scene_composer.html`):**
- `buildZX3D`: `Sound` → `AudioDestination` for zone ambients + dwell. `gain="0"` on destination = silent until SoundFader activates. `containerField="children"` on all AudioClips.
- `buildZX3D`: `SoundFader_<sid>` Script now sets `dest.gain` (not `snd.intensity`) on enter/exit
- `exportX3D` + `buildX3DString`: Music and Bed now emit `AudioDestination` with `containerField="children"`
- SoundFader ROUTEs emitted in both export paths

**Loader changes (`mccf_x3d_loader.html`):**
- `spLoadSceneSound`: fetches `_scene.xml`, caches `_spSceneMusicTrack` / `_spSceneBedTrack`, populates panel labels, calls `spBuildZoneGeometryFromXml`
- `spBuildZoneGeometryFromXml`: clears `_SP_ZONE_GEOMETRY` before rebuild (no stale zone merging)
- `spStartSceneTracks`: restarts `loop=false` Music clip via SAI after gesture unlock; looping Bed left to AudioDestination
- `_resumeAudioContext`: exhaustive X_ITE AudioContext finder (3 paths + fallback unlock)
- `spStopAll`: sets `stopTime` on all known clips; called from `pbStop`
- `spSetVol`: writes to `AudioClip.gain` directly
- Canvas load guard: `spInit` only runs when `x3d-file` selector has a value
- Startup retry: polls `/scene/x3d/list` every 1s up to 15 attempts before calling `x3dLoadFiles`
- Hardcoded garden_002 zone fallback removed from `spDiscoverZones`

### X3D Architecture (permanent record — updated)

```
Track 1: Music   — scene root, AudioDestination, loop=author-set, gain=author-set
Track 2: Ambient — inside Zone Transform, AudioDestination gain=0, SoundFader activates
Track 3: Bed     — scene root, AudioDestination, loop=author-set, gain=author-set  
Track 4: Dwell   — inside Zone Transform, AudioDestination, loop=false, fires on dwell
```

**X3Dv4 node pattern (confirmed working):**
```xml
<!-- Global track — auto-plays on scene load -->
<AudioDestination DEF="SoundNode_Music" gain="0.81">
  <AudioClip DEF="Clip_Music" containerField="children"
      url='"media/Propinquity.mp3"' loop="false" gain="1.0"/>
</AudioDestination>

<!-- Zone ambient — silent until SoundFader fires -->
<AudioDestination DEF="SoundNode_temple_Ambient" gain="0">
  <AudioClip DEF="Clip_temple_Ambient" containerField="children"
      url='"media/TempleOfInanaTheme.mp3"' loop="false" gain="1.0"
      startTime="-1" stopTime="-2"/>
</AudioDestination>
<Script DEF="SoundFader_temple" directOutput="true" mustEvaluate="true">
  <field name="isActive" type="SFBool" accessType="inputOnly"/>
  <![CDATA[ecmascript:
  function isActive(val, time) {
    var clip = Browser.currentScene.getNamedNode("Clip_temple_Ambient");
    var dest = Browser.currentScene.getNamedNode("SoundNode_temple_Ambient");
    if (val) {
      if (dest) dest.gain = 0.8;
      if (clip) { clip.stopTime = -2; clip.startTime = Browser.currentTime; }
    } else {
      if (clip) clip.stopTime = Browser.currentTime;
      if (dest) dest.gain = 0;
    }
  }
  ]]>
</Script>
<ROUTE fromNode="Prox_temple" fromField="isActive" toNode="SoundFader_temple" toField="isActive"/>
```

**Key facts:**
- `AudioClip.gain` is volume (not `Sound.intensity` — Sound node is X3Dv3)
- `containerField="children"` required on all AudioClips feeding into AudioDestination or BiquadFilter
- `startTime="-1" stopTime="-2"` = never auto-fires (SAI-triggered clips only)
- `loop=false` Music clip: AudioDestination starts it at time=0, loader SAI restarts it on gesture
- `SoundFader` sets `dest.gain` to fade in/out (AudioDestination.gain, not Sound.intensity)

---

## Known Bugs Carried Forward

| Bug | Where | Notes |
|-----|-------|-------|
| Music starts on scene load before Play | loader | AudioDestination fires at time=0. Acceptable. Could gate with `enabled=false` and SAI-enable on Play. |
| Zone sound lost on composer reload | composer | `_restoreChorusFromXml` not restoring zone sound fields. Investigate `editZone`/`confirmZone` path. |
| `spInit` shows 0 zones | loader | `spDiscoverZones` SAI enumeration races with scene load. Zones still work via `spBuildZoneGeometryFromXml`. |
| behavior timers retry exhausted for Salida | loader | `DefaultTimer_Salida` not found — H-Anim not assigned. Expected for cylinder avatar. |
| Jack/Cindy/Gardener timers not found | loader | Arc has 4 agents, scene only has Salida. Expected for testScene1. |
| `pbPushPosition: no cultivar in wp` | loader | Empty waypoint object at end of arc. Minor — does not affect playback. |
| Beach zone ambient URL lost on rebuild | composer | Zone sound not persisted through zone rebuild. Part of zone sound restore bug above. |

---

## Next Session Primary Tasks (Day 47)

### Priority 1 — Zone sound restore bug
Zone sound assignments are lost when composer reloads a scene XML. The `_restoreChorusFromXml` path restores scene sound but zone sound fields are not coming back. Fix `_restoreChorusFromXml` to restore zone sound including ambient URL, gain, loop, filter settings, dwell URL/gain.

### Priority 2 — garden_002 re-export
Re-export `garden_002.x3d` from the updated composer so it uses `AudioDestination` instead of the old `Sound` nodes. Test full garden_002 scene with Jack, Salida, Cindy, Gardener.

### Priority 3 — Zone ambient trigger test
testScene1 ProximitySensor triggers camera (viewer), not avatar. Need avatar-position-based zone detection. `spZonePoll` uses avatar Translation node polling — confirm `spTriggerZone` fires `SoundFader_temple.isActive` when Salida enters temple radius. Check console for `SoundFader_temple: ENTER`.

### Priority 4 — Dwell sound wire-up
`Clip_{id}_Dwell` fires on dwell timer complete. Loader already has dwell callback in `pbReleaseDwell`. Wire `Clip_{safeId}_Dwell` startTime in dwell callback.

---

## Bigger Picture (unchanged from Day 45)

1. **Cameras + Lights tab** in loader
2. **Avatar scaling fix** — Salida/Jack mismatch
3. **Pivot/facing direction** — avatars face direction of travel
4. **Character prompt authoring** — Salida brief (200 words)
5. **ElevenLabs + SSML emotion mapping** — gate: sound confirmed stable ✓ (gate passed Day 46)
6. **Reaper bridge testing**
7. **Scene player script** — headless playback
8. **User's Guide + System Manual** — sound architecture section

---

## End of Day 46 Test Results

- [x] Wind (Bed) plays and loops on scene load ✅
- [x] Propinquity (Music) plays once on Play, does not loop ✅
- [x] Stop button stops all audio ✅
- [x] Sound panel shows correct filenames from scene XML ✅
- [x] Zone geometry populated from scene XML (temple, beach) ✅
- [ ] Zone ambient fires on avatar enter — not yet confirmed
- [ ] Dwell sound fires — not yet wired
- [ ] Chorus display — not yet confirmed

---

## The Reaper Vision (keep visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

---

*GitHub NOT current. Commit after Day 47 test confirms green.*
*Session C is done. Zone ambient trigger and dwell wire-up are Day 47 bricks.*
