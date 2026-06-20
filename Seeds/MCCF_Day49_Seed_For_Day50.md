# MCCF Day 50 Session Seed — Handoff from Day 49

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Needs commit after Day 50 testing confirms green. Last commit `93784f3` on master (Day 48 — Days 49 not yet committed).
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**

---

## System Status — End of Day 49

**Sound engine complete at architecture level.**
- Bed auto-fire bug fixed (`enabled="false"` belt-and-suspenders + SAI enable on Play).
- Zone ambients firing on all three zones with 300ms gain ramp fades.
- Dwell sound pipeline wired end to end — needs isolated test to confirm firing.
- Convolver (reverb) in the graph — composer UI complete, export logic complete.
- Media directory structure confirmed: `static/x3d/media/` is canonical root.
- Dropdown sources separated: ambient←`media/`, dwell←`media/soundeffects/`, convolver←`media/convolver/`.
- Chorus reliably firing at final waypoint with Ollama dialogue. ✅
- Path walk WP1→WP2→WP3 confirmed. ✅

**Dope sheet / cinematics editor:** mockup complete, architecture decisions deferred to Day 50.

**GitHub NOT current. Commit after Day 50 test confirms green.**

---

## Working File State

| File | Location | Status |
|------|----------|--------|
| `mccf_x3d_loader.html` | `static/` | Day 49 — dwell SAI wiring, `_agentSegZoneMap`, Bed enabled=false fix |
| `mccf_scene_composer.html` | `static/` | Day 49 — SoundFader always emitted, ramp fades, Convolver UI + export, subdir dropdowns |
| `mccf_api.py` | root | Day 49 — `/media/list` now scans `static/x3d/media/`, supports `?subdir=` and `?ext=` params |
| `testScene3.x3d` | `static/x3d/` | Day 49 — SoundFader on all 3 zones with ramp, Clip_Bed enabled=false, Dwell nodes on all zones |
| `testScene3_scene.xml` | `scenes/` | Day 48 — waypoint `zone` attributes may be empty (see Priority 1) |
| `testScene3_zones.xml` | `zones/` | Day 48 |

---

## Day 49 Work Completed

### Sound Engine — Bed Auto-Fire Fixed
X_ITE ignores `startTime="-1" stopTime="-2"` guard on `loop="true"` AudioClips at AudioDestination
init time. Fix: `enabled="false"` on `Clip_Bed` in X3D. Loader `spStartSceneTracks` sets
`enabled=true` before firing SAI startTime. `spStopAll` sets `enabled=false` after stop so
Stop→Play cycles stay clean. Both composer export paths emit `enabled="false"` on `Clip_Bed`.

### Sound Engine — Zone Ambients All Zones
Composer previously only emitted `SoundFader_{sid}` Script and ROUTE when ambient sound was
assigned at export time. Zones without sound got no fader, no route — adding sound later in the
loader panel had no trigger. Fixed: both branches (sound assigned / no sound) now always emit
SoundFader Script and ROUTE. ROUTE emission ungated. All three zones confirmed working.

### Sound Engine — 300ms Gain Ramp on Zone Enter/Exit
`SoundFader` Scripts upgraded from hard `dest.gain = value` to a 15-step JS `setInterval` ramp
over 300ms. Applies to all zones on export. `FADE_MS` and `STEPS` constants at top of each Script
for easy tuning.

### Sound Engine — Dwell Wire-Up
New module-level `_agentSegZoneMap = {}` in loader maps `{safeName: {segNo: zoneId}}`.
Built in `_buildPivotCacheFromSceneXml` alongside pivot cache — walks `Path/PathWaypoint`
sequence, looks up zone from `_waypointZoneMap` or `Waypoint[zone]` attribute in scene XML.
`pbReleaseDwell` fires `Clip_{zoneId}_Dwell` via SAI after dwell timer starts.
**Known issue:** dwell may not fire if `testScene3_scene.xml` waypoints have empty `zone`
attributes. See Priority 1.

### Sound Engine — Convolver (Reverb)
Full pipeline: composer zone sound panel has Convolver IR dropdown (WAV only from
`media/convolver/`) + Normalize checkbox. Export wraps AudioClip (and BiquadFilter if present)
in `<Convolver containerField="children">` when IR assigned. Zone card shows reverb filename
in purple. X3D Dwell nodes added to all zones (Zone1, Zone2, Zone3) in testScene3.x3d.

### Media Directory Architecture
- Canonical root: `static/x3d/media/`
- `media/` — ambient/music (mp3, wav, all formats)
- `media/soundeffects/` — dwell stingers (mp3, wav, all formats)
- `media/convolver/` — reverb IRs (wav only — Web Audio ConvolverNode requires uncompressed PCM)
- API `/media/list` updated: scans `static/x3d/media/`, supports `?subdir=convolver` and `?ext=wav`
- Loader ambient dropdown ← `media/` root
- Loader dwell dropdown ← `media/soundeffects/` via `refreshSoundEffectsList()`
- Loader convolver dropdown ← `media/convolver/` WAV only via `refreshConvolverList()`

### Dope Sheet / Cinematics Editor
Mockup built (HTML interactive). Architecture decision deferred to Day 50.
Key decisions needed:
- **Option A** — export to X3D interpolators (baked, standalone, no JS at runtime)
- **Option B** — export cue list JSON, loader fires SAI at runtime (arc-synced, flexible)
- Recommendation: Option B — MCCF events are arc-driven not clock-driven; cues snap to
  waypoint arrivals rather than absolute time.

Stage view (top-down layout) will host camera and light placement, same as zones/waypoints.
New "Cinematics" tab in composer alongside Zones, Waypoints, Paths.

---

## Day 50 Primary Tasks

### Priority 1 — Isolated sound feature tests (new test scene)
Create a minimal testScene_sound.x3d with one zone, one waypoint, one path. Test each
feature in isolation:
- [ ] Dwell fires on waypoint arrival (check `zone` attr on waypoint in scene XML first)
- [ ] Convolver audibly affects ambient sound
- [ ] 300ms fade on zone enter/exit is perceptible
- [ ] Bed does not fire on load; fires on Play; stops on Stop

**To fix dwell:** Open composer, edit each waypoint, confirm zone dropdown has correct zone
selected, re-save, re-export scene XML and X3D. The `zone` attribute must be non-empty on
`<Waypoint>` elements in `testScene3_scene.xml` for `_agentSegZoneMap` to populate.

### Priority 2 — Dope sheet architecture decision + begin implementation
Review Option A vs Option B (see above). Begin with camera cut track only:
- Composer "Cinematics" tab with stage view showing camera pins
- Place cameras on top-down layout, assign to Viewpoint nodes
- Timeline track: camera cuts snapping to waypoint arrivals
- Export: cue list JSON (Option B) or X3D Viewpoint/TimeSensor (Option A)
- Loader: fire viewpoint switch via SAI on waypoint arrival event

### Priority 3 — GitHub commit
All Day 48 + Day 49 work. Confirm green test first.

---

## Known Bugs Carried Forward

| Bug | Where | Notes |
|-----|-------|-------|
| Dwell may not fire | loader / scene XML | `zone` attr on waypoints likely empty in current scene XML. Fix: re-author waypoints in composer with zone assigned, re-export. |
| Arc waypoints in reverse order | loader / arc recorder | WAYPT3→WAYPT2→WAYPT1 in arc XML but walk is correct. `_sceneArcRows` build order. Low priority. |
| `_pivotAgentToSegment` cache miss | loader | Cache keyed `id_N`, lookup uses int index. Cosmetic — avatar doesn't face travel direction for non-Cindy avatars. |
| `BodyMat_Cindy` not found | loader | Material node missing from Cindy X3D. Cosmetic. |
| `pbPushPosition: no cultivar in wp` | loader | Empty terminal waypoint. Minor. |
| `spInit` shows 0 zones | loader | `spDiscoverZones` SAI races with scene load. Non-blocking. |

---

## Sound Engine Architecture (permanent record — Day 49)

```
Track 1: Music    — scene root AudioDestination, loop=author-set, SAI-started on Play
Track 2: Ambient  — inside Zone Transform, gain=0, SoundFader Script ramps gain on enter/exit
                    Optional: BiquadFilter (lowpass), Convolver (reverb IR) in chain
Track 3: Bed      — scene root AudioDestination, enabled=false at load, SAI enables+starts on Play
Track 4: Dwell    — inside Zone Transform, loop=false, SAI fires on dwell timer expiry
```

**Convolver chain (ambient with reverb):**
```xml
<AudioDestination DEF="SoundNode_Zone3_Ambient" gain="0">
  <Convolver containerField="children" url='"media/convolver/VoxengoFile.wav"' normalize="true">
    <AudioClip DEF="Clip_Zone3_Ambient" containerField="children"
        url='"media/ambient.mp3"' loop="true" gain="1.0"
        startTime="-1" stopTime="-2"/>
  </Convolver>
</AudioDestination>
```

**Bed guard pattern (confirmed working):**
```xml
<AudioClip DEF="Clip_Bed" ... startTime="-1" stopTime="-2" enabled="false"/>
```
```javascript
// spStartSceneTracks:
bClip.enabled = true;
bClip.stopTime = tNow - 0.01;
bClip.startTime = tNow + 0.05;
// spStopAll:
bClip.stopTime = tNow;
bClip.enabled = false;
```

**SoundFader ramp pattern (confirmed working):**
```javascript
var FADE_MS=300; var STEPS=15;
// ramp sets dest.gain via setInterval staircase
// Enter: ramp(0 → ambientGain), start clip
// Exit:  ramp(curGain → 0), stop clip after FADE_MS
```

---

## Dope Sheet — Design Notes (Day 49)

### X3D nodes available for cinematics
- **Camera** — `Viewpoint` + wrapping `Transform`; SAI `setField` or `NavigationInfo jump=true`
- **Fog** — `Fog` node, `color` + `visibilityRange` fields
- **Background** — `Background` node, `skyColor`, `groundColor`, texture URLs
- **Lights** — `PointLight`/`DirectionalLight`/`SpotLight` — `intensity`, `color`, `on`
- **Transparency** — `Material.transparency` 0→1 per object; fade out, teleport Transform, fade in
- **Movie textures** — `MovieTexture` on geometry, same startTime/stopTime SAI pattern as AudioClip
- **Color interpolation** — `ColorInterpolator` → ROUTE, or SAI ramp

### Transparency trick (permanent record)
Fade character transparency to 1 (invisible), set Transform translation to new position,
fade back to 0 (visible). With `NavigationInfo jump=true` on the destination Viewpoint,
camera snaps without transition artifact. Convincing teleport / ghost effect.

### ElevenLabs integration notes (permanent record)
- Streaming API: good for Ollama-driven generative responses (ephemeral, different each run)
- Cached WAV/MP3: good for authored/scripted lines (one-time generation cost, reusable)
- Cached files enter the Web Audio graph → reverb/filter on dialogue possible
- Streaming bypasses Web Audio → always dry signal
- Dramatic distinction: authored lines have acoustic presence; generative responses are disembodied

---

## Bigger Picture (updated Day 49)

1. **Dope sheet / cinematics editor** — Day 50 start ← NEXT
2. **Sound feature isolation tests** — Day 50 start ← NEXT
3. **ElevenLabs integration** — gate: sound stable ✓ (Day 49)
4. **Avatar scaling fix** — Salida/Jack mismatch
5. **Character prompt authoring** — Salida brief (200 words)
6. **Reaper bridge testing**
7. **Scene player script** — headless playback
8. **User's Guide + System Manual** — zone trigger + sound sections now documentable
9. **Multi-avatar collision behavior** — flag planted Day 48

---

## The Reaper Vision (keep visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

---

*GitHub NOT current. Commit after Day 50 test confirms green.*
*Day 49 complete: sound engine architecture finished, convolver wired, dope sheet mockup built.*
*Day 50 bricks: sound isolation tests, dope sheet implementation begin, GitHub commit.*
