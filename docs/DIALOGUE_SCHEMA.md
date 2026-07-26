# MCCF Dialogue Decoupling — Schema v1

*Item 5a's schema work, scoped as full decoupling (not the incremental
option). Moves dialogue from nested-inside-`<Waypoint>` to a scene-level
`<Dialogue>` container so a line's trigger can be any scene event
(`scene-start` / `touch` / `zone` / `sensed` / `declared`), matching the
Actor model's trigger vocabulary (design doc §3.1) instead of being
hard-coupled to waypoint arrival.*

## Why decouple, concretely

The real system today (`mccf_scene_composer.html`'s `exportSceneXML`,
`mccf_api.py`'s `load_scene_xml`) nests `<Question>`/`<Response>`/
`<Statement>` elements inside each `<Waypoint>`, and the only thing that
fires them is the arc-recording logic reaching that waypoint. There's no
`mode` (static/improv) or `blocking` field anywhere in the real schema —
both were speculative in the Day 71 prototype, not yet real. Decoupling
fixes both problems in one pass: dialogue gets its own container with its
own trigger, and the two missing fields become real schema, not UI-only.

## Grammar

```xml
<Dialogue>
  <Line id="line_cindy_001" actor="Cindy" type="Question"
        mode="improv" blocking="false" trigger="scene-start">
    How does the water feel today?
  </Line>

  <Line id="line_cindy_002" actor="Cindy" type="Response"
        mode="static" blocking="true" trigger="sensed:line_cindy_001"
        ttsText="[thoughtful] Cool. Cooler than I expected."
        tagSource="algorithmic">
    Cool. Cooler than I expected.
  </Line>

  <Line id="line_jack_001" actor="Jack" type="Statement"
        mode="static" blocking="false" trigger="zone:Pool"
        ttsText="[sad] He always did like the water more than the rest of us."
        tagSource="authored"
        audioFile="audio/jack_pool_001.mp3" audioSource="recorded">
    He always did like the water more than the rest of us.
  </Line>

  <Line id="line_jack_002" actor="Jack" type="Statement"
        mode="static" blocking="false" trigger="declared:58">
    Did you feel that?
  </Line>
</Dialogue>
```

Placement: a top-level child of `<Scene>`, sibling to `<Waypoints>` and
`<Paths>` — not nested inside either.

## Field rules

| attribute  | required | values                                                        |
|------------|----------|----------------------------------------------------------------|
| `id`       | yes      | scene-wide unique (same identity discipline as build item 1)  |
| `actor`    | yes      | an agent/Actor name in the scene                               |
| `type`     | yes      | `Question` \| `Response` \| `Statement`                        |
| `mode`     | yes      | `static` \| `improv`                                           |
| `blocking` | yes      | `true` \| `false`                                               |
| `trigger`  | yes      | one of the six (seven, with legacy) forms above                |
| text (elem body) | yes | the line text                                                |
| `ttsText`  | no       | delivery-tagged text for TTS, e.g. `[whisper] text` — see below |
| `tagSource`| co-required with `ttsText` | provenance of the tag — see below         |
| `audioFile`| no       | path to rendered/recorded audio for this line — see below      |
| `audioSource` | co-required with `audioFile` | provenance of the audio — see below |

## `ttsText` / `tagSource` — delivery tag and its provenance

`ttsText` is the text actually sent to a TTS engine: the untagged `text`
body with an optional ElevenLabs emotion-tag prefix, per the placement
convention `/voice/preview` already implements
(`build_tts_text` in `mccf_voice_api.py` — tag immediately precedes the
segment it modifies, no attempt to place multiple tags at word offsets).
Absent `ttsText` means "deliver `text` as-is, no tag" — this is the
overwhelmingly common case for any line nobody has opened in the Dialogue
editor yet, not an error.

Whenever `ttsText` is present, `tagSource` must be present too — a tag
with no recorded provenance means nobody can tell later whether it's a
disposable heuristic guess or a deliberate authorial choice, which is
exactly the ambiguity this field exists to remove. `tagSource` is a
compact string, parsed the same way `trigger` is:

| written as               | parses to                                          |
|---------------------------|-----------------------------------------------------|
| `algorithmic`              | `{type:'algorithmic'}`                              |
| `authored`                  | `{type:'authored'}`                                 |
| `llm-interpreted:<name>`    | `{type:'llm-interpreted', name:'<name>'}`           |

- `algorithmic` — produced by `/voice/preview`'s heuristic
  (`suggested_tag`). **Not trustworthy as a final delivery choice until
  the Day 73 calibration fix has been in production use for a while** —
  the fix corrects the two confirmed failure modes (near-max arousal on
  ordinary short lines; hedging language mis-read as anger), but an
  algorithmic tag is still a suggestion, not a verified-correct one.
- `authored` — picked from a dropdown or hand-typed by a person. The
  editor UI (not yet built) is expected to auto-promote a line from
  `algorithmic` to `authored` the instant a human edits its tag — that's
  an editor-behavior decision, not something `dialogue-xml.js` enforces
  itself, since the parser/serializer has no concept of "an edit just
  happened."
- `llm-interpreted:<name>` — produced by a long-collaboration LLM partner
  via the Kate export/import loop (see below), not called by the system
  directly. `<name>` is a free-text slot, not hardcoded to any one
  collaborator.

## Kate (or any long-collaboration LLM partner) export/import

Implemented in `dialogue-xml.js`'s `exportForKate` / `importFromKate`
(priority queue item 5). **Format revision, on record:** the Day 72 seed
doc §7 originally decided to reuse Chorus's own `build_transcript()`
bracket convention (`[line_id] Speaker: "text"`) for this. That's
superseded — export is plain `<Dialogue>` XML, this schema's own format,
not a second convention invented for the purpose. The bracket convention
existed specifically so `[line_id]` could make strict-id-first reimport
possible; `<Line id="...">` already does that job, so reusing it means
zero new parsing logic and zero risk of two formats drifting apart.

- `exportForKate(lines)` — just `serializeDialogueBlock(lines)`. No
  instructions embedded in the XML itself; what a collaborator is asked to
  do with it is a prompt-authoring concern, not part of the export format.
- `importFromKate(kateXml, originalLines, collaboratorName)` — reconciles
  a collaborator's returned XML against the lines that were sent:
  - **Strict id match** — a returned line whose `id` matches one that was
    sent is treated as an edit to that line.
  - **Fallback to exact-text match** — if the id doesn't match anything
    (regenerated or mangled) but the `text` exactly matches a line that
    was sent, it's still treated as an edit to that line, and the
    **original id is kept** — a returned id never overrides a resolved
    one, same identity discipline as build-schedule item 1.
  - **Genuinely new lines** — no id or text match means the collaborator
    authored something new. Her id is trusted only if it doesn't collide
    with anything already in use; otherwise a fresh `kate_import_<n>` id
    is assigned.
  - Any returned line carrying `ttsText` with no `tagSource` gets one
    auto-stamped as `llm-interpreted:<collaboratorName>` — an explicit
    `tagSource` already present on a returned line is never overwritten.
  - Returns `{ lines, updatedIds, addedIds, valid, errors }` — the
    reconciled set, run through `validateDialogueLines`, but **not
    applied to anything**. Merging into the scene's real `<Dialogue>`
    block is a deliberate author action afterward, same "promotion isn't
    automatic" discipline as Chorus's per-take capture.

## `audioFile` / `audioSource` — rendered/recorded audio and its provenance

`audioFile` is a path to whatever audio actually represents this line —
placeholder TTS render or final hired-actor take, MCCF doesn't distinguish
at the schema level which it's looking at except through `audioSource`.
This is deliberate: the ElevenLabs/TTS pipeline is supported, not a
permanent part of MCCF (it's *"an edit convenience, an inexpensive way to
get voices"*, expected to often be replaced by recorded voice actors for a
published version) — `audioSource` is what makes "still placeholder" vs.
"final VO" a visible scene state instead of something tracked only in the
author's head.

Whenever `audioFile` is present, `audioSource` must be present too, same
co-requirement logic as `ttsText`/`tagSource` and for the same reason — an
audio path with no recorded provenance can't be trusted or distrusted by
anyone who didn't personally render it. `audioSource` is a compact string,
parsed the same way:

| written as                  | parses to                                       |
|-------------------------------|--------------------------------------------------|
| `elevenlabs`                    | `{type:'elevenlabs'}`                           |
| `recorded`                       | `{type:'recorded'}`                             |
| `other-engine:<name>`             | `{type:'other-engine', name:'<name>'}`          |

`audioFile`/`audioSource` and `ttsText`/`tagSource` are independent pairs —
a line can have a delivery tag with no rendered audio yet (still being
drafted), or rendered/recorded audio with no `ttsText` at all (recorded
straight from an actor reading the bare `text`, no TTS involved, no tag
ever generated). Neither pair implies the other.

None of these four attributes are touched by the legacy-migration path —
a line synthesized from a waypoint-nested `<Question>`/`<Response>`/
`<Statement>` gets none of them, same as it gets no real trigger beyond
`legacy-waypoint:<name>`. They only appear on lines that have actually
been through the (not-yet-built) Dialogue editor or an equivalent manual
edit.

`trigger` is a single compact string, parsed into `{type, param}`:

| written as             | parses to                                    |
|-------------------------|----------------------------------------------|
| `scene-start`            | `{type:'scene-start'}`                       |
| `touch:<sensorName>`     | `{type:'touch', sensor:'<sensorName>'}`      |
| `zone:<zoneId>`          | `{type:'zone', zone:'<zoneId>'}`             |
| `sensed:<lineId>`        | `{type:'sensed', lineId:'<lineId>'}`         |
| `declared:<seconds>`     | `{type:'declared', time:<seconds> (number)}` |
| `arc-complete`           | `{type:'arc-complete'}`                      |
| `arc-complete:<zoneId>`  | `{type:'arc-complete', zone:'<zoneId>'}`     |

A `sensed` trigger's `lineId` must reference another `id` in the same
`<Dialogue>` block (or fail validation) — same "identity must resolve"
discipline the dispatcher already enforces for `sensed` steps generally.

## `arc-complete` — Chorus firing as a Dialogue trigger

Added for the Chorus redesign (Day 72 seed doc §5.2): a Chorus firing with
a configured `voice_actor` produces a real `Line` eligible for the same
export pipeline as any other dialogue — but Chorus firing genuinely
doesn't fit any of the other five triggers (it isn't a waypoint touch, a
zone entry, a chained `sensed` response, a fixed-time `declared` beat, or
the one-shot `scene-start`). It fires **asynchronously at arc completion**,
which needed its own trigger kind rather than being forced into one of the
existing five.

Two forms, same bare-vs-parameterized pattern as `scene-start`/`zone`:

- **`arc-complete`** (bare) — fires on *any* arc completing, scene-wide.
  Unconditional, like `scene-start`'s "fires once, no qualifier."
- **`arc-complete:<zoneId>`** — fires only when the arc for that specific
  zone completes. Matches Chorus's actual configuration shape (one
  `<Chorus>` per `<Zone>`, design doc — see seed doc §5.1).

In the dispatcher, `arc-complete` steps go through the same collision-
policy handling as `declared` steps (`onCollision`: interrupt/wait/overlap)
rather than the simpler unconditional `start()` that `scene-start`/`zone`/
`touch` use — an arc completing can just as plausibly collide with
something already running on a track as a scripted `declared` beat can.

Per-take capture (seed doc §5.2, *"at the point we record lines, we quit
making them"*) means a Chorus-voiced line isn't automatically merged into
the scene's permanent `<Dialogue>` block on firing — promotion is a
deliberate author action afterward. A `<Line>` with an `arc-complete`
trigger sitting in a saved `<Dialogue>` block therefore represents a line
that *has* been promoted, not a live subscription that re-fires every time
some arc completes.

## Legacy migration (backward compatibility)

A scene with no `<Dialogue>` element at all is not an error — it's simply a
scene authored before this schema existed. On load, every legacy nested
line (`<Waypoint>`'s `<Question>`/`<Response>`/`<Statement>` children) is
synthesized into this same shape, with:

- `trigger="legacy-waypoint:<waypointName>"` — a sixth, explicitly-marked
  trigger form meaning "fires on arrival at this named waypoint, exactly as
  it always did." This is deliberately **not** silently reinterpreted as a
  `sensed` or `zone` trigger — the author gets to decide the real
  replacement trigger when they actually touch that line, not have one
  assumed on their behalf.
- `mode="improv"` and `blocking="false"` as defaults, since those are
  genuinely unset in legacy data (improv is what the current LLM-driven
  arc-recording flow already does for a `Question` with no authored
  `Response`; `false` for blocking preserves current non-blocking behavior).
- `id` synthesized as `<waypointName>_<index>` if the legacy line has no id
  of its own (it never did — ids are new).

Legacy waypoint-nested `<Question>`/`<Response>`/`<Statement>` elements are
**left in place, untouched**, alongside the new `<Dialogue>` block — this
migration is read-side only (what `load_scene_xml` hands back to a client),
not a rewrite of the file on disk. A scene only gets a real `<Dialogue>`
block on disk once something actually saves through the new path.

## Round-trip / merge contract

Because `/scene/save/scene` has no merge semantics (whole-file overwrite),
an editor that only touches dialogue must not reconstruct the rest of the
scene from the JSON the load endpoint returns — that JSON is lossy relative
to the full XML (it doesn't carry zone weights, chorus config, camera
protos, etc.). Instead: fetch the **raw XML** via `/scene/load/scene/raw`,
replace only the `<Dialogue>…</Dialogue>` block textually (inserting one
before `</Scene>` if absent), and post the modified raw text back —
everything outside that block passes through byte-identical.
