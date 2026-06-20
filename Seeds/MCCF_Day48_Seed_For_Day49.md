# MCCF Day 49 Session Seed — Handoff from Day 48

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Needs commit after Day 49 testing confirms green. Last commit `93784f3` on master (Day 48 not yet committed).
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**

---

## System Status — End of Day 48

**Zone ambient trigger confirmed working.** `SoundFader_Zone2: ENTER` / `EXIT` fires correctly as avatar enters and leaves zone. ProximitySensor → SoundFader pipeline proven on testScene3.
**Chorus fires at final waypoint.** Ollama generates evocative dialogue from coupler state. TTS speaks lines.
**Path bug fixed.** Consecutive duplicate waypoint guard added to composer — `addToPath` blocks double-click at entry time; `exportSceneXML` strips consecutive duplicates on export.
**Clean scene workflow confirmed.** testScene1/garden_002 deleted. testScene3 is the working test scene.

- Music (Track 1) — `startTime="-1" stopTime="-2"` guard in X3D; SAI fires on Play only ✅
- Bed (Track 3) — **BUG: fires on scene load** — testScene3.x3d needs re-export with guard (see Priority 1)
- Zone ambients (Track 2) — `SoundFader_<sid>` Scripts + ROUTE from `Prox_<sid>` — **CONFIRMED WORKING** ✅
- Stop button calls `spStopAll()` — stops all clips ✅
- Chorus fires at final waypoint with coupler-driven Ollama response ✅

**GitHub NOT current. Commit after Day 49 test confirms green.**

---

## Working File State

| File | Location | Status |
|------|----------|--------|
| `mccf_x3d_loader.html` | `static/` | Day 48 — unchanged from Day 47 |
| `mccf_scene_composer.html` | `static/` | Day 48 — consecutive duplicate waypoint guard added (addToPath + exportSceneXML) |
| `testScene3.x3d` | `static/x3d/` | Day 48 export — **Bed needs re-export with startTime="-1" stopTime="-2" guard** |
| `testScene3_scene.xml` | `scenes/` | Day 48 export — clean: 1 zone, 3 waypoints, 1 path (WP1→WP2→WP3 confirmed) |
| `testScene3_zones.xml` | `zones/` | Day 48 export |
| `mccf_api.py` | root | Day 45 — `/media/list` endpoint present |
| `mccf_reaper_bridge.py` | root | Untested |

**Deleted (Day 48 clean slate):** testScene1.x3d, testScene1_scene.xml, testScene1_zones.xml, garden_002.x3d, garden_002_scene.xml, garden_002_zones.xml

---

## Day 48 Work Completed

### Path Duplicate Bug Fixed (composer)

**Root cause:** `addToPath()` allowed the same waypoint to be clicked twice consecutively, producing `["WP1","WP1","WP3"]` in `pathSeq`. This was written straight to scene XML and the arc recorder replayed it faithfully.

**Fix — two guards in `mccf_scene_composer.html`:**
- `addToPath(n)`: checks `pathSeq[pathSeq.length-1] === n` before pushing. Blocks consecutive duplicate, shows toast. Non-consecutive repeats (WP1→WP2→WP1) allowed — valid choreography.
- `exportSceneXML`: `_prevWp` sentinel skips consecutive duplicate `PathWaypoint` refs on export. Console warning emitted if triggered.

### XML Restore — `else` Branch Fixed (composer)

When server already has paths populated (from prior session), `_restoreChorusFromXml` was only patching `waypointOrder` from XML, not `waypoints`. Fixed: `else` branch now restores full `waypoints` array from `PathWaypoint` refs in XML. XML is authoritative for path sequence.

### Zone Ambient Trigger Confirmed (loader)

No code changes needed. `SoundFader_Zone2: ENTER` / `EXIT` confirmed in console. ProximitySensor fires on viewer (camera) proximity, not avatar — viewpoint must be attached to avatar transform for trigger to fire. **Author must select an avatar-attached viewpoint before hitting Play.**

### End of Day 48 Test Results

- [x] Cindy walks WP1→WP2→WP3 correctly ✅
- [x] Zone ambient fires on enter (`SoundFader_Zone2: ENTER`) ✅
- [x] Zone ambient stops on exit (`SoundFader_Zone2: EXIT`) ✅
- [x] Chorus fires at final waypoint ✅
- [x] Ollama generates coupler-driven dialogue ✅
- [x] TTS speaks lines ✅
- [ ] Bed fires on scene load — testScene3.x3d re-export needed
- [ ] Dwell sound not yet wired
- [ ] Arc records waypoints in reverse order — scene XML path order to check
- [ ] `_pivotAgentToSegment: missing waypoints` cache key mismatch — cosmetic

---

## X3D Architecture (permanent record — Day 48)

```
Track 1: Music   — scene root, AudioDestination, loop=author-set, gain=author-set
Track 2: Ambient — inside Zone Transform, AudioDestination gain=0, SoundFader activates
Track 3: Bed     — scene root, AudioDestination, loop=author-set, gain=author-set
Track 4: Dwell   — inside Zone Transform, AudioDestination, loop=false, fires on dwell
```

**X3Dv4 Music/Bed pattern (confirmed working):**
```xml
<!-- startTime=-1 stopTime=-2: guard against AudioDestination auto-fire at scene load -->
<AudioDestination DEF="SoundNode_Music" gain="0.35">
  <AudioClip DEF="Clip_Music" containerField="children"
      url='"media/OrchestraChorus1.mp3"' loop="false" gain="1.0"
      startTime="-1" stopTime="-2"/>
</AudioDestination>
```

**spStartSceneTracks SAI pattern (loader):**
```javascript
clip.stopTime  = tNow - 0.01;  // clear guard
clip.startTime = tNow + 0.05;  // fire ~50ms from now
```

**Zone ambient trigger — CONFIRMED WORKING:**
- ProximitySensor fires on camera/viewer proximity
- Viewpoint must be inside avatar Transform for trigger to work
- Author selects avatar-attached viewpoint before Play
- `SoundFader_<zoneId>` sets `AudioDestination.gain` on enter/exit

**Key facts (unchanged):**
- `AudioClip.gain` is volume (not `Sound.intensity`)
- `containerField="children"` required on all AudioClips feeding AudioDestination
- `SoundFader` sets `dest.gain` on zone enter/exit

---

## Next Session Primary Tasks (Day 49)

### Priority 1 — Fix Bed auto-fire (testScene3.x3d re-export)
Re-export `testScene3.x3d` from updated composer. Verify `Clip_Bed` has `startTime="-1" stopTime="-2"` guard. Confirm wind.mp3 does NOT fire on scene load — only on Play.

### Priority 2 — Dwell sound wire-up
In `mccf_x3d_loader.html`, `pbReleaseDwell`, after dwell timer fires, add:
```javascript
var dwClip = scene.getNamedNode('Clip_' + safeId(zoneId) + '_Dwell');
if (dwClip) {
  var tNow = X3D.X3DExecutionContext ? ... // use same tNow pattern as spStartSceneTracks
  dwClip.stopTime  = tNow - 0.01;
  dwClip.startTime = tNow + 0.05;
}
```
Need to confirm: what `zoneId` is available at `pbReleaseDwell` call time? Check waypoint's `zone` field in the arc step data.

### Priority 3 — Arc waypoint reverse order
Arc is recording WAYPT3→WAYPT2→WAYPT1 but Cindy walks WP1→WP2→WP3. Upload `testScene3_scene.xml` and inspect `<Path>` waypoint order. Likely `_sceneArcRows` is being built from `wps` array in reverse, or `wps` is reversed at restore time.

### Priority 4 — Pivot cache key mismatch
`_pivotAgentToSegment: missing waypoints for Cindy seg 1 — cache keys: 1,id_1` — the cache is keyed by `id_N` but lookup uses integer index. Minor cosmetic but avatar doesn't pivot to face direction of travel. Fix when convenient.

---

## Known Bugs Carried Forward

| Bug | Where | Notes |
|-----|-------|-------|
| Bed fires on scene load | testScene3.x3d | Re-export with startTime="-1" stopTime="-2" guard. Priority 1. |
| Arc waypoints in reverse order | loader / arc recorder | WAYPT3→WAYPT2→WAYPT1 in XML but walk is correct. Investigate `_sceneArcRows` build order. |
| `_pivotAgentToSegment` cache miss | loader | Cache keyed `id_N`, lookup uses int index. Avatar doesn't face travel direction. Cosmetic. |
| `BodyMat_Cindy` not found | loader | Material node missing from Cindy X3D. Cosmetic. |
| `pbPushPosition: no cultivar in wp` | loader | Empty terminal waypoint. Minor, does not affect playback. |
| `spInit` shows 0 zones | loader | `spDiscoverZones` SAI races with scene load. Non-blocking. |
| Dwell sound not wired | loader | `Clip_{safeId}_Dwell` exists in X3D. Wire `startTime` SAI in `pbReleaseDwell`. Priority 2. |

---

## Bigger Picture (unchanged from Day 45)

1. **Cameras + Lights tab** in loader
2. **Avatar scaling fix** — Salida/Jack mismatch
3. **Pivot/facing direction** — avatars face direction of travel (Priority 4 above)
4. **Character prompt authoring** — Salida brief (200 words)
5. **ElevenLabs + SSML emotion mapping** — gate: sound stable ✓, scene restore stable ✓, zone trigger stable ✓ (Day 48)
6. **Reaper bridge testing**
7. **Scene player script** — headless playback
8. **User's Guide + System Manual** — zone trigger section now documentable

---

## Theoretical Foundations — Filed for Future Reference

### Avatar Collision + Emotional Field Dynamics
*Status: Planted flag. Day 48 observation: single-avatar linear path confirmed. Multi-avatar collision behavior TBD.*

When two avatars share a waypoint or collide in transit — if friends, they greet and move apart; if not friends, conflict behavior. X3D Collision node as substrate. Emotional field geometry made visible: proximity as constitutional pressure, collision as coupler interaction event.

### MCCF Coherence Transport Geometry
*Status: Planted flag. Prerequisites: dwell sound wired, ElevenLabs integrated, 100+ arc runs, arc schema formalized.*

The seven couplers may be coordinates of a coherence manifold. The Witness→Steward arc is a path through a space that has shape.

*Reference: MCCF_FUTURE_TRANSPORT_GEOMETRY.md (generated June 2026, in outputs)*

### BAML Assessment
*Status: Noted. Entry point: dialogue generation (Salida speech) before coupler update functions.*

### Technē (x3d_mcp) Assessment
*Status: Noted. Applicable when MCCF moves to programmatic scene generation via MCP.*

---

## The Reaper Vision (keep visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

---

*GitHub NOT current. Commit after Day 49 test confirms green.*
*Day 48 complete: path bug fixed, zone ambient trigger confirmed, chorus + Ollama dialogue working.*
*Day 49 bricks: Bed re-export, dwell sound wire-up, arc reverse order fix.*
