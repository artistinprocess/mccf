# MCCF Day 44 Session Seed — Handoff for Day 45

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Current as of Day 44. Commit `93784f3` on master.
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**

---

## System Status — End of Day 44

**The system works.** Zone sound plays. TTS speaks. Arc fires. Field ticks.
Avatars move. Music and speech running simultaneously. GitHub current.

---

## Working File State

| File | Location | Status |
|------|----------|--------|
| `garden_002.x3d` | `static/x3d/` | Production — sound architecture complete |
| `mccf_x3d_loader.html` | `static/` | Production — sound panel integrated |
| `mccf_reaper_bridge.py` | root | New — OSC/MIDI bridge, untested |
| `mccf_api.py` | root | Day 43 state |
| `mccf_scene_composer.html` | `static/` | Needs sound tab — P0 this session |
| `cultivar_Jack.xml` | `cultivars/` | Jack description written by author |
| `cultivar_Salida.xml` | `cultivars/` | Clean |
| `garden_002_scene.xml` | `scenes/` | Needs sound XML schema added |
| `garden_002_zones.xml` | `zones/` | Needs sound properties added |

---

## P0 This Session — Scene Composer Sound Tab

### What needs to happen
The sound panel in the loader is currently stateless — file assignments
are lost on scene reload. Sound must persist in the scene XML so the
author builds it once in the scene creator and it hydrates automatically
on every load.

### The four-track architecture (decided Day 44, do not re-discuss)

```
Track 1: Music        — scene root, global, loop=true
Track 2: Zone Ambient — inside Zone Transform, loop=true, fade in/out on avatar enter/exit
Track 3: Scene Bed    — scene root, global, loop=true (wind, birds, atmosphere)
Track 4: Waypoint     — inside Zone Transform, loop=false, fires on avatar dwell
```

Music and Bed: at scene root, spatialize=false, maxFront=999
Zone Ambient and Dwell: inside Zone Transform, spatialize=false, maxFront=60

### The X3D node chain (decided Day 44, do not re-discuss)

Simple tracks (Music, Bed, Dwell):
```xml
<Sound DEF="SoundNode_Music" spatialize="false" intensity="1.0" priority="0.9">
  <AudioClip DEF="Clip_Music" containerField="source"
             url='"media/track.mp3"' loop="true" gain="0.7"
             startTime="-1" stopTime="-2"/>
</Sound>
```

Zone Ambient with BiquadFilter:
```xml
<Sound DEF="SoundNode_Garden_Ambient" spatialize="false" intensity="0.0"
       priority="0.5" maxFront="60" maxBack="60" minFront="5" minBack="5">
  <BiquadFilter containerField="source" type="lowpass"
                frequency="900" qualityFactor="1.0">
    <AudioClip DEF="Clip_Garden_Ambient" containerField="children"
               url='"media/water.mp3"' loop="true" gain="0.8"
               startTime="-1" stopTime="-2"/>
  </BiquadFilter>
</Sound>
```

Key facts confirmed from X_ITE spec:
- `AudioClip.gain` (SFFloat, default 1.0) — use this for volume, not Sound.intensity
- `AudioClip.containerField="source"` — required, not inferred reliably
- `startTime="-1" stopTime="-2"` — never auto-fires, SAI sets startTime on trigger
- `BiquadFilter`, `Gain`, `Convolver` — Sound component level 2, X3D 4.0, confirmed in X_ITE

### The scene XML schema (to be written into scene creator)

```xml
<!-- In garden_002_scene.xml or equivalent -->
<SceneSound>
  <Track id="music" url="media/garden_theme.mp3"
         loop="true" gain="0.7"/>
  <Track id="bed"   url="media/birds_wind.mp3"
         loop="true" gain="0.5"/>
</SceneSound>
```

```xml
<!-- In zone definition -->
<Zone id="Garden" ...>
  <SoundDesign>
    <Track id="ambient" url="media/garden_water.mp3"
           loop="true" gain="0.8" spatialize="false"
           maxFront="60" filter="lowpass"
           filterFreq="900" filterQ="1.0"/>
  </SoundDesign>
</Zone>
```

```xml
<!-- In waypoint definition -->
<Waypoint id="Garden_WP1" zone="Garden" agent="Jack">
  <SoundDesign>
    <Track id="dwell" url="media/bell_soft.mp3"
           loop="false" gain="0.85"/>
  </SoundDesign>
</Waypoint>
```

### Three-session build plan
- **Session A (today):** Scene composer — add Sound tab to zone editor,
  write four-track XML schema into scene/zone/waypoint XML on author input
- **Session B:** X3D generator — update scene exporter to write correct
  Sound/BiquadFilter/AudioClip chains into garden_002.x3d from XML
- **Session C:** Loader — update hydration to read sound XML on scene load,
  populate AudioClip urls, start Bed and Music on load, fix Stop button,
  fix volume sliders (write to AudioClip.gain not Sound.intensity)

**Upload `mccf_scene_composer.html` first. XML validation pass before editing.**

---

## Known Bugs To Fix (not today — log only)

| Bug | Where | Notes |
|-----|-------|-------|
| Volume sliders don't work | loader sound panel | Write to AudioClip.gain not Sound.intensity |
| Stop button doesn't stop sound | loader | Add spStopAll() to Stop handler |
| Loop always on | loader sound panel | Add loop toggle per track, write to AudioClip.loop |
| Dwell sound not wired to waypoint | loader + X3D | Needs waypoint-level dwell URL from XML |
| SoundFader prox_* writes SFFloat not SFBool | SoundFader script | Minor — works but type is loose |

---

## Bigger Picture — Where We Are

### What works today
- Arc fires, avatars move on path ✅
- TTS speaks with two voices (Zira + Mark) ✅
- Zone ambient sound plays, fades on zone exit ✅
- MCCF field ticks — coherence, tension, EBPS live ✅
- Greek Chorus fires at arc complete ✅
- Sound panel renders in loader left column ✅
- GitHub current at commit 93784f3 ✅

### What's next after sound persistence
1. **Cameras + Lights tab** in loader (after sound tab in composer)
   - Zone viewpoints already in scene: VP_Garden, VP_pool, VP_Village_Plaza
   - Avatar viewpoints: VP_Jack_Eye, VP_Jack_Side etc.
   - Emotion-driven cuts: tension > 0.7 → close-up, coherence peak → overview
   - Reads from window._lastFieldData already polling

2. **SFX tab** — Fog, Background sky color, particle systems
   - X3D Fog node: fogType LINEAR/EXPONENTIAL, visibilityRange
   - All SAI-writable in real time
   - Persists in scene XML same pattern as sound

3. **Character prompt authoring**
   - Jack description written — test it, measure response quality vs. generic
   - Write Salida brief (200 words: emotional register, history, voice)
   - Write Anna the Librarian brief (Kate's analysis as foundation)
   - Tight Q lines → specific R lines. Generic Q → generic R.

4. **ElevenLabs + SSML emotion mapping**
   - EBPS → prosody wrapper function ~40 lines
   - E drives pitch variance + expressiveness
   - B drives pace, P drives assertiveness, S drives warmth
   - Gate: sound confirmed stable first

5. **Reaper bridge testing**
   - Install loopMIDI, create port "MCCF"
   - Reaper OSC control surface on port 9000
   - Name Reaper regions: Garden, Village_Plaza, Pool, Garden_Chorus
   - Run: python mccf_reaper_bridge.py --verbose

6. **More avatars loading**
   - Jack needs HAnim instance (Jin import pipeline)
   - Cindy path rebuild with correct ../avatars/ path
   - Salida walk animation needs new arc built for her

---

## Architecture Decisions — Permanent Record

**ProximitySensors detect viewer camera, not avatars.**
Avatar zone detection = loader JS poll of Avatar_ node translations every 150ms.
Never route ProximitySensor to sound or avatar-aware logic.

**Sound trigger ownership:** Loader JS owns all sound start/stop via SAI.
X3D ROUTEs only handle FadeClock tick. This separation is clean — keep it.

**FadeClock uses cycleTime (SFTime), not fraction_changed (SFFloat).**
Never route SFFloat to SFTime field. Always check ROUTE endpoint types.

**containerField="source" is required on AudioClip.** Always explicit.

**startTime="-1" = never auto-start.** stopTime="-2" = no scheduled stop.
Set startTime via SAI only when url is assigned and playback is wanted.

**AudioClip.gain is the volume control, not Sound.intensity.**
Sound.intensity is the spatial blend scalar. gain is the actual level.

**XML validation is the north star.** First step every session.
Correct by construction. Prove it right before runtime.

**QRS chain directing:** Tight authored Q → specific LLM R.
Generic Q → generic R. The Q is the constraint, not the invitation.

**The Garden's Purpose (Kate's image):**
Not to eliminate difference, but to weave it.
Not to control destiny, but to cultivate potential.
Not to possess power, but to guide its becoming.
The Garden is alive. We all tend it together.

---

## The Reaper Vision (keep this visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

OBS after Reaper. Same architecture, different endpoint.
Reaper → MCCF after OBS. Musicians drive the field.

---

*GitHub is current. Sound plays. Go get lunch.*
*The scene composer sound tab is the next brick.*
