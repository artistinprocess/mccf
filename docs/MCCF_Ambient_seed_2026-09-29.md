# MCCF Ambient Engine Session Seed — 2026-09-29

Paste this whole file at the start of the next session, alongside the Theme
Workshop spec (`MCCF_Ambient_Theme_Workshop_Spec_v0.2.pdf`) and the current copies
of the files listed in section 6. The spec says what to build and why. This file
says what state the code is in, what is decided, and where to start.

Claude has no memory between sessions. Anything not in this file or the spec
has to be re-derived, so bring the files.

---

## 1. Where we start

**Checkpoint 1a of the Theme Workshop spec:** the engine core. Build
`static/js/mccf_theory.js` (scales, pitch space, transforms, voices) and
`static/js/mccf_smf_writer.js` (MIDI-file writer), then a recipe file, then
preview through the existing Player. Acceptance tests are in the spec's
"Phasing and acceptance" table.

Before starting, get from Len:
1. Feedback from colleagues on the spec (he expects few or no changes).
2. Answers to the seven open questions at the end of the spec, or "accept the
   proposals". Proposed defaults: (1) keep alteration of out-of-scale notes;
   (2) natural minor, seventh raised only in dominant chords; (3) export as a
   browser download; (4) widen the right column in Workshop mode; (5) recipe as a
   separate JSON file; (6) **no default** — which track and bars of `badwater.mid`
   is the test melody; (7) assume 4/4 when a file has no time signature.
3. Latest copies of the files in section 6.

## 2. What is built, tested, and confirmed live (2026-09-27 to 09-29)

Tested with a mock-MIDI harness in Node, and confirmed live by Len on the
MOTU UltraLite to Roland rig unless noted.

**Shared player, `static/js/mccf_midi.js`** (loaded by the Ambient page, the
Loader and the Events Editor; exposes `window.MccfMidi`)
- `parseMidiFile`: SMF format 0/1, PPQN. Captures Control Change events per track
  as `track.controllers[ccNumber] = [{tick, value, channel}]`. **Still skips**
  time signature (0x58), key signature (0x59) and pitch bend.
- `Player` class (no DOM): per-track enable, output-channel override and volume;
  sends Bank Select, Program Change, pan, reverb, chorus and Poly On (CC127) before
  playback; resume-from-position rescheduling; Krumhansl-Schmuckler key estimate;
  live tempo; `sounding()` for meters; `panic()`; panic on page close.
- Scheduling: a Web Worker clock plus Web MIDI hardware timestamps, with a
  lookahead that adapts from 0.15 s to 1.5 s when the page stalls. This fixed the
  "MIDI staggers when the movie loads" bug. Console lines report stalls.
- Also exported: GM instrument names, drum-kit names, `trackColor`, `fmtClock`.
- Note shape used everywhere: `{pitch, startTick, durTicks, velocity, channel}`;
  track shape `{index, name, channel, program, notes, noteCount, controllers,
  lengthTicks}`. Parser channels are 0-based, UI channels are 1-based.

**`mccf_ambient.html`**
- Engine modes: Generative, MIDI Theme Player. Theme panel has the clock,
  instrument names, output channel, volume sliders, loop, Poly On, "send file
  patches & pan/FX", "reset channels to file", All Notes Off (panic).
- Note-driven animation (pitch-class ring, ripples, glows) and theme-mode footer
  panels (key, tempo, energy, texture, 12-bar note meter, chord ring).
- **Not yet run:** the older unit tests (24 parser, 19 scheduler, 26 generative
  MIDI-out). The parser and scheduler now live in `mccf_midi.js`, so those tests
  must be re-pointed at it.

**`mccf_x3d_loader.html`**
- Audio cues (`case 'audio'`): reads `<AudioSources>` from the scene XML, plays
  `/static/x3d/<url>`; a looping source stops after the cue duration. The bird
  (`chakor.wav`) works.
- MIDI cues (`case 'midi'`): reads `<MidiSources>`; file fetched and parsed at scene
  load; device matched by name substring; falls back to a crude browser synth if
  not found; `play` and `stop` labels. Silenced on Stop and Reset.
- Scene clock in the transport bar (`⏱ mm:ss.t`, plus `♪` while MIDI plays).
- **Play waits for the scene to load** (`_sceneReadyNow`): scene load event, at
  least 1.5 s, last two fps readings at least 20, X_ITE `loadCount` if exposed,
  20 s timeout; a second click on Play overrides.
- Wind and waves held shut until Play (`Clip_Music` and `Clip_Bed` set
  `enabled=false` at load), and all scene audio, cue audio and MIDI silenced when a
  scene is swapped out or the page closes.

**`mccf_scene_composer.html`**
- Place > MIDI tab: register a MIDI source (name, `.mid` from the media list, device
  hint, tempo scale, loop). Exports and restores `<MidiSources>`. Sends `midi` data
  to the Events Editor and handles `mccf_update_midi`.
- The Music clip is now exported with `enabled="false"`, like the Bed clip.

**`mccf_events_editor_prototype_2.html`**
- New `MIDI` timeline track (`play` or `stop` at t0, plus "Fit duration to file
  length"), a MIDI section in the Stage panel, and a MIDI inspector with per-track
  enable, output channel and volume, plus Audition and Save to Composer.

Scene XML format (what the Composer writes and the Loader reads):

```xml
<MidiSources>
  <MidiSource name="Badwater" url="X3DAssets/media/music/badwater.mid"
              device="ultralite" tempo="1" loop="false">
    <Track index="8" enabled="true" channel="10" volume="110"/>
  </MidiSource>
</MidiSources>
<!-- in <EventCues>: -->
<Cue track="midi" target="Badwater" label="play" t0="5" dur="200.3"/>
```

Media paths resolve as `/static/x3d/<url>`; files live under
`static/x3d/X3DAssets/media/`.

## 3. Test material

`badwater.mid`: format 1, 9 tracks, 480 ppq, about 03:20.3, about 127 bpm, key
estimated A major (Len confirmed). Programs: 39 Synth Bass 2, 5 Electric Piano 2,
24 Acoustic Guitar (nylon), 17 Percussive Organ, 38 Synth Bass 1, 108 Kalimba,
25 Acoustic Guitar (steel), and a percussion track on channel 10 (program 24,
Electronic Kit, 1,472 notes). Rig: MOTU UltraLite to a Roland synth; the device
hint `ultralite` matches it.

## 4. Decisions (full reasoning is in the spec)

Confirmed:
- Ambient stays a standalone side module. Scenes play exported MIDI as-is.
- Transforms run offline in Ambient and export a `.mid`. No real-time
  transformation in scenes.
- Phasing: 1a engine, 1b-i grid view, 1b-ii notation view, 1c harmony, then 2, 3.
- Live input starts as step entry. Real-time recording comes later. Reaper stays the
  tool for serious recording.
- Grid (piano roll) view first, then notation. Notation is read-only (VexFlow, in
  its own file, Ambient only). MusicXML export is a later add-on.
- The Theme Composer is its own tab in the Ambient page, so the animation stays on
  the Visualizer tab. Transport and export live in a bottom bar, matching the
  Loader. Mockups: Grid view, Notation view, Visualizer tab.
- Field-driven parameters are deferred, but every numeric control is registered so
  it can be bound later.

Proposed in the spec, awaiting a yes: diatonic pitch space by default; a result is
a recipe plus a seed; three rule sets (Chorale-strict, Organum-parallel, Free).

## 5. Known gaps and parked items

- Zone and waypoint sound start logic in the Loader was not touched. It works, but
  the audio "enter" and "exit" issue Len mentioned is unaddressed.
- The X3D `BasicAudioSource` PROTO 404s (`static/x3d/protos/mccf_audio_protos.x3d`).
  The audio cue does not depend on it, but anything that does may.
- A stray audio cue at 388.4 s in GardenOfTheGoddess_Scene01 has no target.
- Unknown whether Len's X_ITE build exposes `loadCount`; the guard works without it.
- Episode loader (a list of scenes loaded in succession) is a future idea. The
  scene-swap cleanup above is the groundwork.
- Lip-sync project: fully researched and specified separately; starts after the
  demo. Not part of this thread.
- Ambient research: Len is deciding what the pattern-transform rules should be
  before more is built. Nothing beyond the spec is committed.

## 6. Files to bring

`mccf_ambient.html`, `mccf_midi.js`, `mccf_x3d_loader.html`,
`mccf_scene_composer.html`, `mccf_events_editor_prototype_2.html`, `badwater.mid`,
and the spec. Untouched but relevant: `mccf_ambient_api.py`.

## 7. How this thread works

- Build a little, verify it, build a little more. Each checkpoint ends with a
  listening or viewing session.
- Claude cannot hear the output. Automated checks catch rule violations; Len judges
  the sound.
- Claude verifies with Node harnesses using mock DOM and mock MIDI. Len tests on
  the real rig after a hard refresh (Ctrl+F5).
- Music logic goes in browser-free files so it can be tested in Node. The Loader
  keeps loading only `mccf_midi.js`.
- Changing the parser means re-running the parser tests. Changing Player behavior
  means re-checking the Ambient page and the Loader.
