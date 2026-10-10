# MCCF Ambient Engine / Theme Workshop (AETW) — Session Seed, 2026-10-03

Paste this whole file at the start of the next session, with the current copies of the files in section 7
and the Theme Workshop spec. Claude has no memory between sessions: anything not here or in the files has to
be re-derived. This replaces the 2026-09-29 and 2026-10-01 seeds.

---

## 1. Where things stand

The Theme Workshop is **built through checkpoints 1a, 1b-i, 1b-ii and 1c**, plus several things beyond the
original spec that came out of working sessions. All of it passes its automated tests (1,738 checks in 17
suites, run with `npm test`, see section 6). **None of it has been heard on the real rig by Claude** (Claude
cannot hear) and **only the pieces Len has listened to are musically confirmed.** The page was exercised in
jsdom with mock canvas / Web Audio / Web MIDI, and the pictures in `screenshots/` were drawn by an offscreen
renderer, not by Len's browser. The first job of any session is to ask what Len found.

Built (spec phase in brackets):
- Engine core: scales, pitch space, the ten transforms, voices with entry bars, recipe, source hash, canonical
  SMF writer (byte-identical exports). [1a]
- Grid (piano roll) view: bars/beats, snap lines, ghost of the original theme, playback cursor, piano keyboard
  in the gutter with lit keys, chord strip. [1b-i]
- Notation view (VexFlow 4.2.5, vendored): quantizing, key spelling, accidentals, ties, voices, percussion
  staff, swing straightened to eighths, grand staff for wide-range tracks, chord symbols, page follows the
  cursor. [1b-ii]
- Harmony: chord vocabulary, k-best Viterbi chord paths, voicing under three rule sets, independent rule scans,
  parallel harmony in scale steps. [1c]
- Beyond the spec, Len asked for these: generated drums (jazz-swing, jazz-waltz, straight-rock); hand-edited
  voices ("freeze to edit"); full grid editing (draw, move, resize, multi-select, box select, copy / cut /
  paste / duplicate, velocity lane, velocity ramps, quantize, swing, humanize, drum-named rows); undo / redo of
  the whole recipe; solo; pin and compare; wider right column in Workshop mode.
- Not built (Len said do the Users Guide LAST, "for MCCF end to end"): the Users Guide itself.

## 2. Decisions (confirmed unless marked)

- Ambient stays a standalone side module. Scenes play exported MIDI as-is. Transforms run offline.
- A result is a **recipe plus a seed**. Same recipe + same source file => identical bytes. The recipe carries
  the source SHA-256 and the engine version; a replaced source file is detected and warned about.
- **Freeze-then-edit** (confirmed by Len): any generated voice (transformed, drums, harmony) can be frozen into
  hand-edited notes stored in the recipe. What you hear does not change. Edits never stay "linked" to a
  generated voice. Harmony freezes into TWO voices (chords and `<id>_bass`).
- Diatonic pitch space by default; chromatic per transform. Out-of-scale notes keep their alteration under
  transposition and mirror under inversion. Natural minor; the seventh is raised only in dominant chords.
- Rule sets: `chorale-strict`, `organum-parallel`, `free` (parallels, crossing, spacing, ranges, leading tone,
  seventh resolution, cadence placement per the spec table; crossing is an error only under strict).
- Harmony weights are named in the recipe (`harmony.weights`: melodyFit, transition, cadence, voiceLeading,
  stylePenalty).
- Field coupling (EBPS driving parameters) is still deferred. Every numeric control is meant to be bindable
  later; no binding exists yet.
- Reaper stays the DAW. Len tests exports in Guitar Pro 8 and on the MOTU UltraLite -> Roland rig.

## 3. Architecture

Files (all under `static/`, page at `static/mccf_ambient.html`, scripts in `static/js/`):

| File | Role | Browser-free? |
|---|---|---|
| `mccf_midi.js` | parser + Player (shared with the Loader and Events Editor). Added: time/key signatures, per-channel programs, `Player.audition()`. **Len's 24 parser tests have NOT been re-run against it.** | yes |
| `mccf_theory.js` | pitch space, transforms, recipe (normalize / validate / build), voices, `freezeVoice`, `editHandNotes`, `makeParallel`, drums generator, fingerprint, SHA-256, recipe digest | yes |
| `mccf_harmony.js` | chords, windows, k-best paths, voicing, rule scan | yes |
| `mccf_smf_writer.js` | canonical Standard MIDI File writer | yes |
| `mccf_grid.js` | piano-roll layout, painting, and the **pure pointer/keyboard editing model** | layout and model yes; painting needs a canvas context |
| `mccf_notation.js` | MIDI -> score model (pure) and VexFlow drawing | model yes |
| `vexflow-4.2.5.js` | vendored, pinned (MIT, licence file alongside) | |

The page has four inline `<script>` blocks after the library tags: **main** (Len's original, with small hooks),
**Workshop** (recipe UI), **grid UI**, **notation UI**. In Claude's workspace those three blocks were edited
as `workshop_block.js`, `grid_block.js`, `notation_block.js` and re-embedded; **the page file Len holds is the
truth now.** Next session, edit the inline blocks in the page directly.

`build(recipe, parsedFile)` is the one entry point: -> `{recipe, theme, arrangement, voices[], warnings, shiftTicks}`.
`arrangement` is parser-shaped (play it, write it with `writeSMF`, draw it). Page flow: edit recipe ->
`changed()` -> `rebuild()` -> write SMF -> `themePlayer.load()` -> grid / notation refresh. Preview equals export.

## 4. Recipe format (what a `.recipe.json` holds)

Top level: `recipeVersion, engine{name,version}, source{file,sha256,tracks[],bars[a,b]}, key{tonic,scale},
ruleSet, seed, harmony{weights}, backing{enabled,leadInBars,tailBars}, voices[]`.

Voice kinds (all have `id, name, entryBar, program, channel (1-16), volume, enabled`, optional pan/reverb/chorus):
- ordinary: `source` ('theme' or a voice id), `chain[{type,version,params}]`
- `kind:'drums'`: `style, intensity, swing, fillEvery, humanize, ending, bars('auto'|n), seed`, channel always 10
- `kind:'notes'` (hand-edited): `notes[{p,s,d,v}]` in VOICE-LOCAL ticks (entryBar places it), optional `frozenFrom`
- `kind:'harmony'`: `source, style, rhythm, vocab, inner, bass, inversions, spacing, k, path, seed,
  bassProgram, bassChannel, bassVolume` -> two tracks, `<id>` and `<id>~bass`

Rules: other voices may derive from ordinary and hand voices, NOT from drums or harmony. The voice graph must
be acyclic. Edit operations (`editHandNotes`): add, move, resize, delete, velocity (vel | dVel | set{id:vel}),
paste, quantize, swing, humanize. Dragging a note earlier than a voice's entry lowers `entryBar` by whole bars so
nothing else moves.

## 5. Known gaps, limits and "clean up afterwards" list

Len chose to push ahead quickly and clean up later. Likely cleanup, roughly in priority order:
1. Run Len's 24 parser tests + 19 scheduler + 26 generative-MIDI-out tests against the modified `mccf_midi.js`
   (the Loader and Events Editor load it too; changes were additive but unverified there).
2. Look at everything in a real browser: the 460 px Workshop column with the harmony block (long), toolbar
   crowding in the Grid tab (three rows of controls), keyboard shortcuts feel, wheel behaviour.
3. Roland check: GM2 drum kits via Program Change on channel 10 (Jazz 32, Brush 40), program changes for the
   new tracks, channel clashes with source tracks (the panel warns).
4. The Workshop panel is one long scroll; the spec wanted four collapsible sections.
5. **Tuplets are the one unfinished item of the notation polish** (grand staff and chord symbols are done). Tuplets are not engraved: swing is shown as straight eighths; real triplets are snapped to the 16th grid
   (the status line says so). Chord-tone-heavy tracks use a simple treble/bass split at middle C.
6. Harmony limits: seven-degree scales only (pentatonic / hexatonic borrow the parent scale); no secondary
   dominants, tritone substitution, borrowed chords or jazz ii-V-I yet (phase 2 "chromatic color"); a melody
   that leaves no room below it for the requested voices produces a result and an honest `range` violation.
   Windows are split where the melody spans more than 14 semitones.
7. Pasting uses an in-page clipboard only. No click-to-seek on the grid ruler. Chord strip cells are not
   clickable (the spec lists a "clickable chord strip" as later).
8. Velocity ramps apply to every note under the line unless some are selected.
9. Staff labels come from MIDI track names (badwater shows "Track 4").

## 5b. Harmony audit, 2026-10-03 (what changed, and why)

Len returned after a medical interruption; the harmony engine had been built in an earlier pass whose report he
never received, so it was **audited with independent scripts, not by trusting the test suites**. Findings and fixes:
1. **Seeded tie-break noise was too large.** Default `jitter` was 0.12; through the recipe pipeline it tipped
   Reflections to a stray III in bar 5 in 26 of 60 seeds (the module test passed only because it used `jitter: 0`).
   Now 0.015 (a tie-breaker, not a dice roll): 60 of 60 seeds give pure i V. Regression test goes through `build()`.
2. **`parallelInfo` mislabelled pentatonic intervals** (it used 7-note names). It now names the interval from the
   scale's real semitones. **Spec correction (v0.2 text is wrong):** in a pentatonic scale two steps is mostly a
   perfect FOURTH (4 or 5 semitones), three steps is a perfect fifth (flagged under Chorale-strict), four steps
   sevenths/sixths. The spec's "two steps gives a sixth" must be fixed when v0.3 is written. Parallel harmony itself
   was always counted in scale steps (`makeParallel` = ordinary diatonic-transpose voices), which is the span process.
3. **The leading-tone rule now covers the bass** (it only checked inner voices): V6 -> i6 with the bass leaping
   C#->F was accepted. Sevenths stay inner-voices-only.
4. **"Why that chord?"** Every window carries `why`: `{chosen, rivals[2], margin, text}` with the four cost terms
   (melody fit, progression, cadence, style) at the recipe's weights, neighbours held fixed. Shown by hovering the
   grid's chord strip (hint line), in a collapsible list in the harmony block, and in `windows[i].why`.
Independent hand-checks that passed: harmony never at or above a sounding melody note; bass and inner ranges;
leading tones resolve (18/19 before fix 3, 19/19 after); chord sevenths resolve down or hold; inversion policies
(`root` = 0 of 14 bass notes off the root, `first`/`smooth` = 5 of 14); rebuilds byte-identical.
Lesson to keep: when a feature arrives without a report, verify its claims on the real files before repeating them.

## 6. Tests

`npm install` (jsdom, vexflow; node-canvas optional, only for the screenshots), then `npm test`. Suites:
theory, hand, drums, writer, harmony, harmony_voice, grid, grid_edit, notation, notation_draw, page, page_drums,
page_grid, page_notation, page_edit, page_harmony, page_workflow (about 1,700 checks). Fixtures `badwater.mid`
and `Reflections2.mid` live in `fixtures/` (the tests find them there). The page tests boot the real page in
jsdom with mock canvas, Web Audio, Web MIDI and a polyfilled SVG `getBBox`; a blocked Google Fonts request
shows up as a harmless "Resource was not loaded" error and the tests ignore it.

Working method that has served well: build a little, verify with tests, Len listens and judges the sound.
When a test fails, decide whether the test or the code is wrong before touching anything. Several "failures"
were wrong test expectations and some were real bugs the tests caught; keep that discipline.

## 7. Files to bring to the next session

`mccf_ambient.html`, `mccf_midi.js`, `mccf_theory.js`, `mccf_harmony.js`, `mccf_smf_writer.js`, `mccf_grid.js`,
`mccf_notation.js`, this seed, the spec, and the fixtures. Untouched and not needed: `mccf_ambient_api.py`,
`mccf_x3d_loader.html`, `mccf_scene_composer.html`, `mccf_events_editor_prototype_2.html` (the Loader and Events
Editor were not changed this round; they still load `mccf_midi.js`).

## 7b. Harmony audition files (`harmony/`, regenerate with `node tools_harmony.js fixtures harmony`)

1 Reflections + organ chords and bass, a chord per bar (i V i V ...) · 2 second-best path (an F major in bar 5) ·
3 chord every half bar, seventh chords (ends on a deceptive cadence) · 4 chords + jazz drums · 5 parallel thirds and
octave · 6 badwater theme with chords (A E A D E A A D E A C#m Bm E A, authentic cadences at bars 3 and 7).
Claude has not heard any of them. Ask Len which chord choices he disagrees with, by bar number, and use the
`why` text for that bar to decide whether the weights or the vocabulary need changing.

## 8. Test material and what it showed

- `badwater.mid` (decades old, 9 tracks, A major): "a tougher test", revealed good surprises. Nylon guitar =
  track index 3 ("Track 4" in the parser). Theme used: bars 10-16. Third / octave below at 2 or 4 bars worked
  "to some degree, some splendidly"; **sixth below did not**. The fifth below (diatonic) did not (a diatonic
  fifth below is sometimes a tritone: the "tonal answer" problem, phase 3).
- `Reflections2.mid` (4-voice canon, 23 bars, D minor / medieval): voices enter at bars 1, 3, 5, 7 at the unison
  and two and three octaves down. The engine regenerates it exactly from the Flute alone. Harmony finds
  **i V i V ... for all 16 bars** (Len: "it's simply I V in D minor"), with the V's seventh counted as part of V.

## 9. What to do next (Len's order)

1. Ask Len what he found testing: editing, groove tools, harmony, notation. Fix what is wrong first.
2. The cleanup list in section 5.
3. Solo / compare: done (solo button per voice; pin this version + "listen to: pinned version"). A labelled history list is not.
3b. Write spec v0.3: fold in the review items, the decisions above, and the pentatonic correction (section 5b).
4. Spec phase 2: embellishment, chromatic color, pedal and ostinato, modal mutation, hocket, tablature, more
   jazz style; phase 3: counterpoint, fugue scaffold, real-time recording.
5. **The MCCF Users Guide, last,** end to end across all of MCCF (this module is one part). Plan: Markdown, a
   section per feature written from the actual gestures, shortcuts and the recipe format, able to become the
   in-app help.
