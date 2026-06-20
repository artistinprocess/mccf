# MCCF Day 45 Session Seed — Handoff for Day 46

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Needs commit after Day 46 testing confirms green. Last commit `93784f3` on master.
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**

---

## System Status — End of Day 45

**The system works.** Zone sound plays. TTS speaks. Arc fires. Field ticks.
Avatars move. Music and speech running simultaneously.
Scene Composer now authors sound into XML and X3D.
Session A and Session B of the sound persistence plan are complete.
GitHub NOT current — commit after Day 46 end-to-end test confirms green.

---

## Working File State

| File | Location | Status |
|------|----------|--------|
| `garden_002.x3d` | `static/x3d/` | Needs re-export from updated composer |
| `mccf_x3d_loader.html` | `static/` | Production — sound panel integrated, Session C pending |
| `mccf_scene_composer.html` | `static/` | Day 45 — sound tab complete, loop controls, media picker |
| `mccf_api.py` | root | Day 45 — `/media/list` endpoint added |
| `mccf_reaper_bridge.py` | root | Untested |
| `cultivar_Jack.xml` | `cultivars/` | Jack description written by author |
| `cultivar_Salida.xml` | `cultivars/` | Clean |
| `garden_002_scene.xml` | `scenes/` | Needs re-export with SceneSound block |
| `garden_002_zones.xml` | `zones/` | Needs re-export with SoundDesign blocks |

---

## Day 45 Work Completed

### Session A — Scene Composer Sound Tab ✅
- Scene Setup panel: Music (Track 1) + Bed (Track 3) URL pickers, gain sliders, loop checkboxes
- Zone form: Sound sub-section — ambient URL, gain, loop, BiquadFilter toggle (freq/Q), dwell URL + gain
- Zone detail panel (right): sound read-only display on zone select
- `confirmZone` collects all sound fields into `z.sound`
- `editZone` restores all sound fields including loop
- `exportZoneXML` emits `<SoundDesign><Track>` blocks
- `exportSceneXML` emits `<SceneSound>` at root + `<SoundDesign>` in zones
- `_restoreChorusFromXml` restores zone sound, scene sound, loop values from raw XML on load

### Session B — X3D Generator ✅
- `buildZX3D` now emits correct Sound/BiquadFilter/AudioClip chains per Day 44 spec
  - Zones with sound: `SoundNode_{id}_Ambient` + `Clip_{id}_Ambient`, optional `_Dwell`
  - Filter branch: BiquadFilter wraps AudioClip with `containerField="children"`
  - Plain branch: AudioClip with `containerField="source"`
  - `startTime="-1" stopTime="-2"` on all clips — SAI triggers, never auto-fires
  - `intensity="0.0"` on zone ambients — loader SAI fades in on zone enter
  - Zones with no sound: disabled stub node so loader panel can still assign at runtime
- `buildX3DString` (Send to Launcher) emits `SoundNode_Music` + `SoundNode_Bed` at scene root
- `exportX3D` (download) same
- Both read from DOM directly — Apply Grid not required before export

### Bug fixes
- `exportSceneXML` read from DOM directly, not `sceneConfig.sound` — Apply Grid no longer required
- Scene Name field updates from loaded scene's XML `id` attribute on load
- `placedAgents` rebuilt from `<EmotionalArc>` blocks if API load response omitted them
- `updateSummary()` called at end of `_restoreChorusFromXml` so name shows correctly
- Loop checkboxes wired through XML, X3D, and load restore — all paths consistent

### Media picker
- All 5 URL fields are `<select>` dropdowns populated from `/media/list`
- `/media/list` endpoint added to `mccf_api.py` — scans `static/media/`, audio extensions only
- MIDI files flagged `[MIDI→Reaper]` in purple — visible but not playable via Web Audio
- ↺ button in Scene Sound panel, auto-fires on ping success
- Graceful fallback if endpoint unavailable

---

## Session C — Next Session Primary Task

### What needs to happen
The loader reads sound data from the scene XML on load and hydrates the live X3D scene.
Currently the loader has a stateless sound panel — file assignments are lost on scene reload.
With Session B done, the X3D now has correct AudioClip nodes with baked URLs.
Session C completes the loop: loader starts Music and Bed automatically, fixes the known bugs.

### Known bugs to fix in Session C (from Day 44 seed, still open)

| Bug | Where | Notes |
|-----|-------|-------|
| Volume sliders don't work | loader sound panel | Write to `AudioClip.gain` not `Sound.intensity` |
| Stop button doesn't stop sound | loader | Add `spStopAll()` to Stop handler |
| Loop always on | loader sound panel | Add loop toggle per track, write to `AudioClip.loop` — composer now owns loop value |
| Dwell sound not wired to waypoint | loader + X3D | Needs `Clip_{zoneId}_Dwell` trigger on dwell timer |
| `SoundFader prox_*` writes SFFloat not SFBool | SoundFader script | Minor — works but type is loose |

### Session C build plan
1. On scene load, fetch scene XML (`/scene/load/scene/raw`)
2. Parse `<SceneSound>` — set `Clip_Music.url`, `Clip_Bed.url`, set `startTime` to trigger playback
3. Parse zone `<SoundDesign>` — confirm `Clip_{id}_Ambient` URLs match (they're now baked in X3D, this is a verify step)
4. Fix volume sliders: write to `AudioClip.gain` via SAI, not `Sound.intensity`
5. Fix Stop button: call `spStopAll()` which sets `stopTime` on all clips
6. Wire `Clip_{id}_Dwell` to fire on dwell timer complete (loader already has dwell callback)
7. Upload `mccf_x3d_loader.html` first. XML validation pass before editing.

---

## Four-Track Architecture (permanent record)

```
Track 1: Music        — scene root, global, loop=author-set, spatialize=false, maxFront=999
Track 2: Zone Ambient — inside Zone Transform, loop=author-set, fade in/out on avatar enter/exit
Track 3: Scene Bed    — scene root, global, loop=author-set (wind, birds, atmosphere)
Track 4: Waypoint     — inside Zone Transform, loop=false, fires on avatar dwell
```

### X3D node DEF naming convention (Session C must match these)
```
SoundNode_Music          — Track 1, scene root
Clip_Music               — Track 1 AudioClip

SoundNode_Bed            — Track 3, scene root
Clip_Bed                 — Track 3 AudioClip

SoundNode_{safeId}_Ambient   — Track 2, inside Zone_* Transform
Clip_{safeId}_Ambient        — Track 2 AudioClip (intensity=0.0, SAI fades in)

SoundNode_{safeId}_Dwell     — Track 4, inside Zone_* Transform
Clip_{safeId}_Dwell          — Track 4 AudioClip (loop=false, fires on dwell)
```
Where `safeId` = zone id with non-alphanumeric chars replaced by `_`
e.g. "Village Plaza" → `Village_Plaza`

### Architecture decisions (permanent)
- `AudioClip.gain` is volume, not `Sound.intensity`
- `startTime="-1" stopTime="-2"` = never auto-fires, SAI sets startTime on trigger
- `containerField="source"` required on AudioClip always explicit
- `BiquadFilter containerField="children"` when filter is present
- `intensity="0.0"` on zone ambients — fade controlled by SoundFader script via SAI
- Loader JS owns all sound start/stop. X3D ROUTEs only handle FadeClock tick.

---

## Bigger Picture — What's After Session C

1. **Cameras + Lights tab** in loader
   - Zone viewpoints: VP_Garden, VP_pool, VP_Village_Plaza
   - Avatar viewpoints: VP_Jack_Eye, VP_Jack_Side etc.
   - Emotion-driven cuts: tension > 0.7 → close-up, coherence peak → overview

2. **Avatar scaling fix**
   - Salida and Jack avatar scale mismatch visible in Day 45 test
   - Cindy path also needs `../avatars/` path rebuild

3. **Pivot/facing direction**
   - Avatars need to face direction of travel — was working, got lost in refactor
   - Translation delta between waypoints → yRotation on Avatar_ Transform

4. **Character prompt authoring**
   - Jack description written — test response quality vs. generic
   - Write Salida brief (200 words: emotional register, history, voice)
   - Tight Q lines → specific R lines

5. **ElevenLabs + SSML emotion mapping**
   - EBPS → prosody wrapper ~40 lines
   - Gate: sound confirmed stable first (Session C)

6. **Reaper bridge testing**
   - Install loopMIDI, create port "MCCF"
   - Reaper OSC control surface on port 9000
   - Run: `python mccf_reaper_bridge.py --verbose`

7. **Scene player script**
   - Load and play scenes in sequence without viewer interaction
   - Control panels hidden/invisible mode
   - Prerequisite: Session C complete and sound reliable

8. **User's Guide + System Manual updates**
   - Sound architecture section: Web Audio vs Reaper split
   - Track ownership table (Track 1–4 + Reaper as live layer)
   - MIDI files note: composer shows them, Web Audio can't play them, route via Reaper
   - Loop controls: authored in composer, persisted in XML/X3D

---

## End of Day 45 Test Checklist (run before committing)

- [ ] Load `garden_002_scene.xml` — scene name updates to `garden_002`
- [ ] Avatars (Jack, Salida) appear on map after load
- [ ] Music and Bed dropdowns populate from `/media/list`
- [ ] Select files, export Scene XML — `<SceneSound>` block present with correct URLs and loop values
- [ ] Export X3D — `SoundNode_Music` and `Clip_Music` present with correct URLs
- [ ] Zone edit → Sound tab → select ambient file → save → export X3D → `Clip_Garden_Ambient` present
- [ ] Play All in loader — avatars move, TTS fires
- [ ] Music plays on scene load (Session C pending — may not auto-start yet)
- [ ] Zone ambient fades in when avatar enters Garden

---

## The Reaper Vision (keep visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

---

*GitHub NOT current. Commit after Day 46 test confirms green.*
*Session C is the next brick. Upload loader first.*
