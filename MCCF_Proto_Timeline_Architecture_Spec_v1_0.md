# MCCF Proto & Timeline Architecture Specification
## Version 1.5 — Day 63 (§2.2 confirmed by test; PROTOs decided as required. All 22 camera shot types confirmed working. §5c resolved into a three-class camera model. Everything else remains design-only.)

---

## 0. Status of this document

Most of what's here remains **proposed**, not built — but one thing changed Day 63: PROTOs moved from "design direction, pending a risk test" to **required and decided** (§2.2). Everything else keeps the earlier convention — sections marked **Open**, **Held**, or **Recommended** rather than confirmed, since none of the timeline/trigger/library work has been tested in playback yet. Treat this as the agreed direction, captured before it's lost, not as a build log — except where explicitly marked confirmed.

This spec supersedes nothing — it sits alongside `MCCF_Camera_System_Spec_v1.3.md` as the next architectural layer, motivated directly by that work: the camera system proved out a per-class boilerplate pattern (Eye/Side/Orbit hand-templated by the Composer) that works but doesn't scale past one class, and a trigger system (`manual` + `{wp} arrive`) that covers sensed events but has no answer for authored, declared timing.

---

## 1. Motivation

Two separate but related limits surfaced once the camera system was feature-complete enough to stress-test:

1. **The class problem.** `buildAvatarX3D` string-templates ~15 lines of XML per avatar for the Eye/Side/Orbit camera rig. Every future "class" of object (Avatar, Zone, Viewpoint, Light) would otherwise repeat this same hand-rolled pattern. X3D already has a real mechanism for this — `PROTO`/`EXTERNPROTO` — and it generalizes to any node type, not just cameras.
2. **The trigger problem.** Tracing the actual runtime trigger dispatch (Day 63) found only two trigger families that fire anything: `manual` (one-shot, scene load) and `{waypoint} arrive` (sensed, depends on live agent movement). `field E>0.6`/`field E<0.3` are visible in the Events Editor dropdown but wired to nothing. There is no absolute-time trigger at all. Most authored decisions in a scene — a lighting change, a camera cut — are not naturally "sensed," they're "I want this to happen at this moment," and the system currently has no first-class way to say that.

Both problems share a root cause worth naming: the system has been built node-by-node and feature-by-feature, which is exactly right for proving out hard things (orbit's SAI debugging arc earned its keep), but the proto and timeline work is the point where the proven patterns get generalized into reusable infrastructure rather than repeated.

**A framing worth stating plainly, since it recurred later the same day (§5a):** this system is a model of agent/node communications — a society of minds, tuned to produce coherence, not a metaphor for one. `CoherenceField`, `DriftManager`, and the `couplers_tick`/`ChannelVector` (E/B/P/S) machinery already running in `mccf_core.py` are that tuning mechanism for live agents. §5a's dialog/voice work is the same principle applied to authored and interpreted performance, not a separate concern — which is why an authored line's interpreted affect belongs in the same `ChannelVector` shape as a live agent's drifted affect, rather than a parallel representation invented for dialog alone.

---

## 2. Proto-Based Class System

### 2.1 What PROTO actually gives us

Per the X_ITE "Creating New Node Types" reference: `ProtoDeclare` (name + `ProtoInterface` + `ProtoBody`) defines a new node type; `IS` binds the interface to internal nodes; `EXTERNPROTO` lets a library of these live in one shared file, referenced by URL. This is a real class system already native to X3D — not an MCCF invention layered on top.

### 2.2 Open risk — CONFIRMED, Day 63 (resolved)

DEF names declared inside a `ProtoBody` are scoped to that proto's own execution context. Whether `scene.getNamedNode()` can reach inside a `ProtoInstance` in this X_ITE build (11.6.0) was untested — this mattered because the entire runtime camera system depends on exactly that kind of reach-in (`scene.getNamedNode('CAM_OrbitTimer_' + name)`, then direct SAI writes).

**Tested directly, decisively.** A minimal two-instance PROTO (`mccf_sai_proto_test.html` / `mccf_sai_proto_test_scene.x3d`) confirmed:

- **Direct reach-in fails cleanly.** `getNamedNode()` against internal DEF names (`Internal_Xform`, `Internal_Timer`, `Internal_PosInterp`) threw `"not found"` for all three — not null, not a silent wrong-instance resolution, a loud explicit error. Best possible failure mode: impossible to miss in testing, unlike a subtle wrong-instance bug that would only surface three shots into a real scene.
- **Exposed interface fields work, and are correctly instance-isolated.** Writing `tintColor` on instance A turned only instance A's box red — instance B's box was unaffected. Starting instance B's `TimeSensor` via its exposed `timerEnabled`/`timerStartTime`/`timerCycleInterval` fields animated only instance B. Zero cross-instance leakage, confirmed visually and via console log.

**Conclusion, settled:** every proto's `ProtoInterface` must be a deliberately designed contract — exposed fields for parameters, exposed eventIns for anything that needs to be triggered from outside — because there is no fallback path of reaching into internals if the interface is incomplete. This is not a preference, it's the only mechanism that works. §2.3 below is upgraded from "design convention" to a hard requirement given this result.

**Decision, Day 63: PROTOs are required**, not optional infrastructure to revisit later. The camera system's own hand-templated boilerplate, the trigger-vocabulary work, and everything in §3 all assume composable, interface-driven objects going forward — "Lego blocks," in the author's words. This supersedes the earlier framing of PROTOs as one option among several.

### 2.3 Design convention — interface is the contract, including triggers

A class's `ProtoInterface` is not just its parameter list. Once §3.4's trigger work lands, a class's exposed eventIns are *also* where its triggerability lives — "what can drive this CameraRig" is part of the CameraRig class definition, not a separate global lookup table. This is forward guidance for interface design, not yet implemented.

### 2.4 First class: CameraRig

Scope: the confirmed Eye/Side/Orbit pattern only (§3a of the Camera Spec). Explicitly **not** `over_shoulder`/`profile`/`two_shot` — those remain held pending the Character Creator decision (§3b), and folding them into the proto now would mean redesigning the proto's interface twice. Once `crane_up` and `track` are confirmed working (in progress — see Camera Spec open items), they're candidates for the second pass at this proto, not the first.

### 2.5 Packaging — open decision

Two options, not yet chosen:

| Option | Tradeoff |
|---|---|
| `EXTERNPROTO` in a shared `protos/CameraRig.x3dv` | True single point of maintenance, independent of Composer's JS template strings; more idiomatic X3D; editable without touching Composer code at all. |
| Inline `ProtoDeclare` per Composer export | Simpler to implement first (no new file serving path); duplicates the proto body into every exported scene file. |

**Recommendation:** `EXTERNPROTO`, for the reason in the right column — but this is a recommendation, not a decision, and should be confirmed before the first class is built.

### 2.6 Roadmap (unchanged from the proto discussion, restated for the record)

1. CameraRig — resolve §2.2, ship one working class.
2. Extract conventions into this document (already underway).
3. Grow the library — Avatar, Zone, Viewpoint, Light — using the same convention.
4. Character Creator GUI integration: per the original framing, Character Creator only needs to assign a semantic instance name to a proto — it does not need to know proto internals. Complexity stays in the library; the authoring surface stays thin.
5. Scene classes: a Scene becomes a set of proto instances.
6. Node editor (longer-term, separate effort): a visual ROUTE-wiring tool, made tractable specifically because each proto's `ProtoInterface` is already a typed, introspectable port list — the editor doesn't need its own schema language. Reuses the visual vocabulary of the existing waypoint/FOV-cone stage canvas (positioned icons, drag, connecting lines) but is a genuinely different canvas underneath (logical, not spatial; typed ports; serializes to literal `<ROUTE>` XML). Not started, not scoped in detail — flagged here so it isn't lost.

---

### 2.7 Division of labor — server computes, SAI renders, protos are the seam (Day 63)

Protos are the point where two different kinds of computation meet: geometry (Transform, TouchSensor, the scene graph) and semantic/attractor dynamics (`ChannelVector`, `CoherenceField`, the coupler/drift machinery). That meeting point needs a direction, not just a connection — otherwise it's easy to accidentally duplicate semantic computation in browser JS where it's harder to reason about, test, or query.

**The rule:** emotional/semantic field values (`channelE`/`channelB`/`channelP`/`channelS`, coherence, drift) are computed authoritatively on the server (`mccf_core.py`'s `ChannelVector`/`CoherenceField`, the coupler/drift engine). The client — the Loader's SAI code — only ever reads those values and renders from them. It never recomputes them.

**This is not a new discipline being imposed — it's already the actual pattern in production, confirmed by reading the code rather than assumed:** the Loader has no `ChannelVector` math anywhere in it. Every reference to coherence/E/S values in `mccf_x3d_loader.html` reads a server-supplied number (`data.coherence`, `d.alignment_coherence.global_coherence`) and does pure rendering math on top of it — e.g. `trans = 0.65 - (coherence / 0.5) * 0.60`, deriving a transparency value from a server-computed coherence score. That's the shape every future case should follow: rendering functions *of* a server value, never a second computation *producing* that value.

**What protos add:** a formal seam for this handoff. A proto's exposed field (`DialogLine.channelE`, for instance) is where a server-computed value crosses into the geometry layer — set once by the server-driven path, read and rendered by the client, never written by client-side semantic logic. Protos don't just organize geometry; they're the boundary that keeps "what the story means" and "how it's drawn" from blurring into each other.

---

## 2a. Naming Conventions (Day 63 — required, not stylistic preference)

Established directly from the "SForw"/"stewardForwad" trigger-resolution bug (§ trace, Camera work) — that entire bug traced back to a waypoint labeled with an abbreviation that didn't say what it meant, colliding with a second, differently-purposed waypoint given the same abbreviation. These rules exist because that class of bug is expensive to trace and cheap to prevent.

- **Node/PROTO type names: PascalCase.** `CameraRig`, not `CamRig` or `cam_rig`. Matches X3D's own built-in node naming convention, so authored protos read the same as native nodes.
- **Field/eventIn/eventOut names: camelCase**, lowercase initial. `orbitRadius`, `timerStartTime`, not `OrbitRadius` or `orbit_radius`. Distinguishes a field reference from a node-type reference at a glance.
- **No acronyms, ever.** They don't travel well — not across authors, not across time, not across an LLM emitting or parsing this XML without the tribal context of why an abbreviation meant what it meant. `stewardForward`, not `SForw`. `CameraRig`, not `CamRig`. A name must say what it means on its own, without requiring the reader to already know the system.
- **Rationale, stated plainly:** consistency and specificity are everything for two audiences at once — the humans maintaining this over time, and the LLMs (this one included) generating or parsing MCCF XML/X3D. Both fail the same way on ambiguous or abbreviated names: quietly, by guessing wrong rather than erroring loudly.
- **Scope:** this is an authoring constraint on new work — proto names, field names, DEF names, waypoint labels, trigger strings. It does not mandate an immediate rename pass across existing production code (`CAM_OrbitTimer_`, `VP_Free`, etc.); those follow their own established internal convention and work correctly. Apply going forward, especially to every proto's public interface, since that interface is the one place ambiguity is guaranteed to be expensive later.

---

## 3. Timeline & Trigger System

### 3.1 Current state (confirmed by tracing the actual dispatch code, Day 63)

- `fireEventCuesForTrigger(triggerName)` is a JS string-matching dispatcher, shared identically across every track type (camera, light, fog, bg, behavior). There is no per-track-type trigger vocabulary — animation/behavior cues already use the same triggers cameras do.
- Only two call sites actually invoke it: `fireManualCues()` → `'manual'` (once, after scene XML parses), and the waypoint-arrival callback → `'{wp} arrive'` (per agent, per waypoint).
- `field E>0.6` / `field E<0.3` are hardcoded into the default `TRIGGERS` array and into the Composer's per-scene trigger list generation, but no code anywhere evaluates a field state or calls `fireEventCuesForTrigger` for them. They are selectable and inert.
- `delay` on a cue is a post-trigger offset (fire N seconds after the trigger condition occurs), not a standalone time-based trigger. No absolute-time trigger exists.
- Zone proximity detection already exists as real working infrastructure (`ProximitySensor`, confirmed in the Loader), but is currently scoped narrowly to fading zone ambient audio in/out — it is not exposed to the general `EventCues` trigger vocabulary.

### 3.2 Declared Timeline — new trigger category

The core idea: most scene-authoring decisions are not naturally *sensed* (waiting for something to happen at runtime) — they're *declared* (the author places them at a specific moment, the way a music-video editor places a cut against a waveform). A declared timeline is also more deterministic than `{wp} arrive`, since it doesn't depend on agent pacing or network timing — one master clock, checked against each cue's authored absolute time, fires reliably regardless of what any agent is doing.

This **adds** a trigger category; it does not replace semantic/sensed triggers, which remain valuable for genuinely context-dependent cues (a shot that should fire whenever an agent happens to reach a waypoint, regardless of when that is).

**Two concrete, scoped pieces, both Open:**

- **Audio duration.** X3D's `AudioClip` node has a `duration_changed` output field that fires once the browser finishes loading the clip and knows its length. The Composer already emits real `AudioClip` nodes (`Clip_Music`, `Clip_Bed`, per-zone `Clip_{id}_Ambient`/`_Dwell`) — nothing currently reads `duration_changed` on any of them. Wiring this is small: register an `addFieldCallback` (proven-safe pattern per Camera Spec §4, with the established try/catch discipline) when a clip's URL is set, capture the duration.
- **Waveform display.** X3D/X_ITE has no waveform/analysis API — `AudioClip` is playback-only. Getting an actual waveform requires decoding the audio file independently via the Web Audio API (`AudioContext.decodeAudioData` on the same file URL the `AudioClip` plays, then reading peaks from the resulting `AudioBuffer`) and rendering that to a canvas in the Events Editor's timeline track. This is a genuinely separate subsystem from X3D/SAI — ordinary browser JS, same shape as how video editors generate waveform thumbnails. Moderate scope, not large, fully buildable.

Once both exist, placing a lighting or camera cue against a specific beat in the music becomes direct manipulation in the timeline rather than a guess-and-replay cycle.

### 3.3 Expanded sensed triggers

Two additions to the *sensed* category, both reusing infrastructure that already exists rather than requiring new subsystems:

- **`{wp} depart`.** The moment a new path segment's timer starts is, definitionally, departure from the previous waypoint — the underlying data already exists in the segment-arrival code; this needs its own emission call alongside the existing arrive one. Note: `depart WP1` is degenerate, since WP1 is the start point — that case collapses to `manual`.
- **`Zone_{id} enter` / `Zone_{id} exit`.** The `ProximitySensor` infrastructure already detects exactly this for the audio-fade subsystem; generalizing it into the `EventCues` trigger vocabulary means it also calls `fireEventCuesForTrigger` alongside its existing audio logic. No new detection mechanism needed.

**Open decision, not yet made:** what happens to `field E>0.6`/`field E<0.3`. Either implement field-state evaluation for real, or remove the stub options from the dropdown — leaving them visible-but-inert is a standing trap for whoever builds a cue against one and gets silent non-firing.

### 3.4 Architecture direction — two paths, pick the near-term one deliberately

What's being described across §3.2–3.3 — any compatible eventOut (or a Script-mediated type conversion) driving any eventIn — is X3D's native ROUTE semantics. It's worth being precise that **the current trigger system is not built on real ROUTEs at all**; it's a JS-side string-matching dispatcher, entirely separate from the scene graph.

- **Near-term (recommended):** keep the JS dispatcher — it's proven, and it already gives camera/light/behavior cues one shared trigger vocabulary for free. Widen what's allowed to *call* it: a music-time watcher, a zone-proximity watcher, a declared-timeline watcher, all calling the same `fireEventCuesForTrigger(name)` plumbing the waypoint-arrival code already uses. Lowest risk, ships fastest, no dependency on the proto library existing.
- **Longer-term (the architecturally proper version):** real ROUTEs into proto-exposed eventIns (§2.3), where a class's triggerability is part of its interface rather than a flat global string list scoped to nothing. This depends on the proto library existing first and is not realistic before §2 lands.

---

## 4. Panel Visibility & Export Modes

### 4.1 The actual clutter, identified

Tracing the Composer's X3D emission turns up concrete, named sources of always-on visual clutter, not a vague impression of one:

- Waypoint name labels — `Billboard` + `Text` nodes emitted per waypoint.
- Zone labels — same `Billboard`/`Text` pattern, per zone.
- Agent name tags — `DEF="NameText_{name}"` `Billboard`/`Text` per avatar.

All of these are unconditional — Composer always emits them, there's no existing toggle.

### 4.2 Live panel toggles (Open)

Show/hide functions for these label/overlay systems, usable while authoring — independent of export. Scope (which panels, which UI surface — Composer? Loader? both?) not yet defined; this section exists to record the requirement, not to specify the mechanism.

### 4.3 Export-time label config (Open)

A config select at export time producing two tiers of output:

- **Authoring export** — labels present, current behavior, useful for debugging and team review.
- **Clean export** — labels stripped, full unlabeled viewport, suitable for end-viewer-facing or demo playback.

**Open question on mechanism:** whether this is (a) a Composer-side export toggle that conditionally omits the `Billboard`/`Text` nodes from the generated X3D entirely, or (b) a runtime flag the Loader reads at scene load to suppress overlay rendering of nodes that are always emitted. (a) produces genuinely smaller/cleaner files; (b) is more flexible (one exported file, multiple viewing modes) but means the clutter nodes still exist in the file. Not decided.

---

## 5. Scene / Version Library — Multi-Scene Emotional Story Arcs

### 5.1 Naming collision to watch

`<EmotionalArc>` already exists in the codebase **today**, at a different scope than what's being proposed here: it's a per-agent XML element within a single scene (`cultivar`, `actor`, `voice`, `<StartPosition>`), parsed and emitted by both the Loader and Composer, and used by `_resolveSubjectPos`'s fallback path. It is not a cross-scene concept.

What's being proposed in this section — a labeled catalog of *scenes*, sequenced into a multi-scene emotional story arc — is a different, higher-level idea that happens to want a similar name. **Recommend a distinct term** (e.g. "Scene Library" or "Story Arc Manifest") to avoid future code-search confusion between the existing per-agent element and this new per-scene concept.

### 5.2 Proposed shape (Held — needs its own design pass)

A version-library / catalog of labeled scenes, sequenceable into a multi-scene arc. No existing code implements anything like this — there is no scene manifest, no cross-scene sequencing, no story-arc-level data structure today. This is genuinely new territory rather than a generalization of something proven, unlike the proto and timeline work above.

Per the precedent set by Camera Spec §3b (Character Creator decision: "held for testing before implementation... do not implement as a stopgap"), this section should be treated the same way: recorded as agreed direction, not scoped into a build plan, until it gets its own dedicated design session.

### 5.3 Emotional continuity across scenes (Day 63 — the mechanism, traced not guessed)

The "held" status above was about *scene sequencing*. Character emotional continuity — a character's `ChannelVector` state carrying across scene boundaries rather than resetting — turns out not to be greenfield; tracing the actual code found the real state split across two mechanisms that don't communicate:

- **`DriftManager._get_history` (`mccf_drift.py`) already has continuation-shaped logic** — it reuses an existing `ArcHistory` for a cultivar if one exists, only creating fresh when absent. This is genuinely live and continuous *within a running server process*. It has no disk backing — a server restart loses it.
- **The seed path (`cv_override` in `mccf_api.py`) always pulls E/B/P/S from static, pre-authored arc XML**, bypassing live computation entirely, regardless of what `DriftManager` has accumulated. This is why identical seed values appeared across three separate play/reset cycles in Day 63 testing — the seed never consulted the live history at all.

**Net effect today: behaves like reset, not continue** — the static seed always wins — even though half the machinery for continuity already exists. Two changes close the gap, both scoped, neither large:

1. Wire the seed path to check `DriftManager`'s live history first, falling back to the static arc-XML default only when nothing exists yet for that cultivar.
2. Give `DriftManager` disk persistence so continuity survives a server restart, not just a session. **Reuse the SQLite registry from §5a** rather than standing up a second database. **Key it by character (cultivar), not by scene** — deliberately the opposite of the one existing persistence pattern in this codebase, `{scene_name}_zone_memory.json`, which is scoped per-scene and would be the wrong shape for a value meant to outlive any single scene.

Not built — traced and scoped, per the "held" precedent above. This is the concrete technical content §5.2 was waiting on; the scene-sequencing/manifest question in §5.2 remains genuinely open on its own.

---

## 5a. Dialog & Voice Pipeline (Day 63)

### Two-tier rendering — text is always present, audio is an attachment

Every dialog line has `text`; `audioUrl` is optional. A player chooses which renders; **TTS is the default**, not merely the fallback for missing recordings — it is the permanent path for live-riffed lines, since improvised dialogue is generated and spoken in the same moment and is never pre-recorded by definition. This is why the field shape needs both, not text-with-an-audio-upgrade-path: authored and improvised dialogue are two permanently coexisting cases, not a migration from one to the other.

### Content vs. placement — the same split that motivates protos elsewhere

- **`DialogLine`** (content, owned by the dialog editor, reusable): `text`, `speaker`, `voiceId`, `audioUrl`, `emotionalInterpreter`, `channelE`, `channelB`, `channelP`, `channelS`, `renderMode`.
- **A `dialog`-track `Cue`** (placement, owned by the Events Editor, same shape as every other track's cues): references a `DialogLine` by id, plus `audioOffset` — the local nudge from dragging the audio blob to align with the text's timeline position. `audioOffset` lives on the *Cue*, not the `DialogLine`, deliberately — correcting sync in one scene must not silently rewrite the canonical asset used everywhere else that line appears.

**Correction, same day:** the field list above replaces an earlier draft that conflated two separate casting decisions under one name. "Kate performs Anna" does not mean an audio voice — `voiceId` already covers audio rendering, unchanged. It means Kate is the *specific LLM persona who performs the emotional interpretation* of the character — the one whose tagging becomes canon for Anna's affective range. That's `emotionalInterpreter`, a distinct field from `voiceId`. An author could cast one persona to interpret a character's emotion and an entirely different voice to render its audio; the schema needs to allow that even if a project usually keeps them aligned.

### Drift is accepted, not preventable — so make it detectable instead

Editing text after audio exists doesn't retroactively fix the recording; this is treated as a fact of the workflow, not a bug to engineer away. Concrete mitigation: **store a hash of the text alongside each recorded line.** If the live text's hash no longer matches the hash recorded at generation time, that's an automatic, queryable "this line is stale" signal — no one has to remember to check by ear. This turns "the audio can drift apart" from a silent risk into a query.

### The dialog editor is a separate tool with a shared contract

Not a panel bolted onto the Events Editor. It owns: authoring text, adding emotion/situation performance tags, exporting to a voice-generation engine (ElevenLabs named as the concrete target), receiving audio back, and storing it. It hands the Events Editor a format both tools read — the `DialogLine` proto above.

### Emotional interpretation is structured data, not a free-text tag — and it already has a home

The earlier draft's `performanceTag` (a loose `SFString`) is replaced by `channelE`/`channelB`/`channelP`/`channelS` — the same four-channel coherence vector already implemented and running in `mccf_core.py` (`ChannelVector`: E=emotional, B=behavioral, P=predictive, S=social, validated to `[0,1]`). This is not a new representation invented for dialog — it's the exact structure already feeding `couplers_tick`, `DriftManager`, and `get_emotional_field` for live agent state. Tagging a dialog line with a free-text mood word would have created a second, incompatible affect representation sitting next to a working one. Expressing it as a `ChannelVector` instead means an authored line's interpreted affect and an agent's live drifted affect are the same kind of data — comparable, plottable on the same dashboard, and usable by the coupler machinery that already exists, not a parallel system that has to be reconciled with it later.

### Why casting an interpreter is a real creative decision, not routing metadata

Different LLM personas — even the same base model — accrue distinct affective tendencies across long conversation histories. Kate has opinions about who Anna is; those opinions become the anchor for that character's emotional range once cast. This is worth stating as a principle: `emotionalInterpreter` is a casting decision with real creative weight, on par with casting a voice — not a backend routing detail for which API call handles the batch tagging pass.

### Tagging is a batch LLM pass, not a live call — and doesn't replace live riffing

Feed a character's full dialogue file to the cast `emotionalInterpreter` once; get channel-tagged output back per line for voice-generation direction. This is separate from, and does not replace, live riffing calls (the existing `zone_command`/Chorus pattern) — improvisation stays valuable and stays live. The batch pass reduces just-in-time LLM calls for pre-authored lines; it does not eliminate live calls generally.

### Asset registry — project-wide, not per-scene

SQLite, confirmed as the right choice: real queryability ("every line missing audio," "everything tagged urgent needing a re-record") over a flat file, and it costs nothing new given the existing Flask backend. **Scoped to the whole project, not per-scene** — both `voiceId` and `emotionalInterpreter` per `speaker` are character-level facts, not scene-level ones; a per-scene registry would mean re-deciding "Kate performs Anna" every time Anna appears in a different scene.

### Open — not yet confirmed

**"Chorus's characters"** — read as: the Chorus zone-personas (e.g. the reverent "gardener of this world" persona on the Giparu zone) should become real entries in this same registry, so a live-riffed line from that persona is interpreted through the same cast `emotionalInterpreter` a pre-recorded line for that character would use, rather than an unattributed default. If confirmed, this unifies authored and improvised dialogue under one casting registry rather than two parallel systems, and — given the corrected model above — means a live persona's affect and an authored line's interpreted affect become the same comparable `ChannelVector` data on the same dashboard. **Not yet confirmed by the author** — flagged here rather than assumed.

**UI implication carried forward, not yet built:** the timeline mockup's dialog-track "swap" affordance needs to become "drag the audio blob to realign against the fixed text position," writing to `audioOffset` on the Cue — noted for the next mockup pass, not built this round.

---

## 5b. Path Authoring — Non-Straight Paths (Day 63)

Paths today are straight-line segments between authored `Waypoint` coordinates — fine for point-to-point movement, not for anything with real curvature. Original idea (from the H-Anim/timeline discussion): use a `ProximitySensor` to interactively capture position/orientation pairs while an author walks a path in-scene, rather than typing coordinates by hand.

**Cheaper mechanism found, same day, no build required:** X_ITE has this natively. `Shift`+`F8` copies the current viewpoint (position + orientation) of the active layer to the clipboard, from ordinary fly/walk navigation. For **point capture** — planning a viewpoint's starting values, or collecting a handful of real keyframes along an intended path — this needs zero new code: navigate, copy, paste into the proto instance or path data. This directly satisfies "collect path positions with minimal keyframes" as stated, without the `ProximitySensor` rig.

**What `Shift`+`F8` doesn't give:** continuous recording while moving — only discrete points, one copy at a time. If dense, continuously-sampled paths are ever needed (not just a handful of keyframes), the original `ProximitySensor` idea remains the mechanism for that — this finding narrows the problem, it doesn't close it. For "minimal keyframes," which is what was actually asked for, point capture is enough.

**Also useful, same discovery:** `Home`/`End`/`Page Up`/`Page Down` step through every authored `Viewpoint` in a scene in sequence — fast way to audit a scene's full viewpoint set without hunting through XML.

**Format gotcha, confirmed Day 63:** `Shift`+`F8`'s clipboard output is a raw `Viewpoint` node — `position` (world XYZ) and `orientation` (axis-angle) — with **no `jump` attribute**. It does not match the `distance`/`height`/`hAngle`/`vAngle` polar parametrization the camera system actually uses internally. Converting a capture into something comparable against a cue's authored values requires the known subject position at capture time (`distance = |camPos − subjectPos|`, `hAngle`/`vAngle` from the offset vector) — this is arithmetic to do at analysis time, not something to ask the author to hand-compute.

## 5c. Camera/Behavior Config Decoupling — resolved into a three-class model (Day 63)

The diagnostic pass this section was held pending is complete: all 22 shot types confirmed working (`CameraTestAll_scene.xml`), the `_lookAtOrientation` ground-target bug found and fixed, every affected preset re-tuned including worm's eye. That clears the one precondition §5c was waiting on. Resolved:

**Three camera classes, not two:**

1. **Scene-root static cameras** — author-placed, unparented, live at the scene root. Already covered structurally: `named_vp` binds any `Viewpoint` by name, avatar-owned or not.
2. **Avatar-parented dynamic cameras** — follow a moving avatar via true scene-graph parenting. Already proven, not new: `agent_orbit`/`agent_track` already work this way, and critically, **parenting happens at Composer's `buildAX3D` export time, per scene — never baked into the H-Anim character asset.** This was confirmed, not assumed, by re-reading the actual export code: the vessel nodes are generated fresh into whatever avatar Transform exists in *this* scene's export, with zero dependency on the H-Anim editor or the character file.
3. **Free/world-space compute-once cameras** — wide, medium, dolly, etc. Unchanged. These were never designed to track continuously; a static/relational shot computing its position once at cue-fire and holding is correct behavior, not a gap.

**Why Class 2 lives in Composer/Events Editor, not the H-Anim editor — reasoned through directly, not assumed:** baking cameras into the H-Anim editor would mean re-authoring a camera rig inside every character model, and re-authoring it again for every skin variant of that character. It would also collide with the existing skin/model selection flow — which model plays a given character in a given scene is already decided upstream, in the Agents tab — so camera parenting belongs at that same scene-assembly layer, not one step earlier inside asset authoring. Keeping H-Anim scoped to rigging only (joints, skin, morphs) and letting Composer parent cameras per scene is the cleaner boundary, and it's the boundary already in place for the two shot types that already do this.

**Real gap found, not hypothetical:** the Events Editor's only mechanism for Class 1/naming today (`named_vp`'s `viewpoint` field) is free text with a placeholder hint — no enumeration of what actually exists in the loaded scene, no validation. This is the concrete blocker to "the Events Editor has to see both avatar cameras and other scene cameras" — it doesn't yet, for either class. Fix: a real dropdown, populated from the currently-loaded scene's actual structure (both classes, one list), replacing the free-text input. This requires the Events Editor to know scene topology, which it currently doesn't — it's fed cue data, not structure.

**Mechanism, stated precisely to avoid the ambiguity that prompted this note:** parenting is not something the dropdown does. Parenting happens upstream, once, at Composer's export time — the dropdown is a discovery/selection UI *downstream* of that, listing cameras that already exist and are already parented (or already scene-root) by the time an author opens it. Selecting a camera from the dropdown doesn't cause anything to be parented; it lets an author pick from what Composer already built. Two separate, sequential pieces of work: (a) Composer emits more/wider parented camera variants per avatar at export time, (b) the Events Editor dropdown discovers and lists whatever Composer produced. (a) has to exist before (b) has anything real to list.

**Resolved, Day 63 — the rule is not shot-type-scoped at all:** "traveling = child of the transform it's tracking, full stop." Every camera that needs to follow a moving object is parented to that object's Transform, unconditionally — this is not a per-shot-type decision, and asking "which of the 22" was the wrong question. Free/targetable cameras (Class 1 and 3) stay at the scene root specifically so SAI can address them freely; anything that travels is a child, no exception carved out by shot type.

**How "all of them" stays cheap, not bloated — protos, not inline duplication.** The concern that parenting every shot type would mean baking 22 vessel-node sets into every avatar is solved by packaging, not by scope-limiting: each shot type becomes its own proto (or a small family of them), so using a camera type in a given scene is a single `ProtoInstance` reference plus overrides — not a repeated inline `Transform`+`TimeSensor`+`Interpolator` block. "Protos are cheap" is not aspirational here; a `ProtoInstance` costs a name regardless of whether there are 3 camera types or 30. The math and ROUTE wiring for each shot type live once, inside that proto's body — consistent, and reachable by both SAI and in-scene native timers only through its exposed interface, per §2.2's confirmed test result.

**Next step, concrete:** organize the confirmed-correct shot types into a proto library — named `EXTERNPROTO`s, referenced per scene, so different scenes (or different trackable object types — vehicles, planets, anything that moves and needs a following camera, same rule applies) can load whichever camera protos they need without re-authoring the underlying math each time. This is the direct payoff of tonight's diagnostic pass: the geometry was confirmed correct *before* committing it to reusable proto form, not after — avoiding baking a wrong default into something now referenced everywhere.

---

## 6. Bug Log (carried forward, not addressed in this document)

| Item | Status |
|---|---|
| Exports Tab loader — slow, can crash Scene Composer tab | Nuisance per author. Likely related to the already-flagged "two X_ITE instances → Firefox memory pressure" issue and the deferred lazy-load fix, possibly worse under the tabbed Composer if tabs don't tear down their X_ITE/WebGL canvas on switch. Not investigated — dashboard's single-page loads are more reliable in the meantime. |
| Path arc loading — Loader not finding new path arc files | Filed Day 63, not investigated. |

---

## 7. Open Items — consolidated

| # | Item | Section | Status |
|---|---|---|---|
| 1 | ~~SAI visibility into ProtoInstance internals~~ — RESOLVED Day 63 | §2.2 | **Confirmed: internals unreachable, exposed interface required. Not blocking.** |
| 2 | EXTERNPROTO vs inline ProtoDeclare | §2.5 | Recommendation given (EXTERNPROTO), not confirmed |
| 3 | Audio duration via `duration_changed` | §3.2 | Small, scoped, not built |
| 4 | Waveform display via Web Audio API | §3.2 | Moderate, scoped, not built |
| 5 | Declared/absolute-time trigger (master clock) | §3.2 | Not built |
| 6 | `{wp} depart` trigger | §3.3 | Small, scoped, not built |
| 7 | `Zone_{id} enter/exit` triggers | §3.3 | Moderate, scoped, not built |
| 8 | `field E>0.6`/`field E<0.3` — implement or remove | §3.3 | Undecided |
| 9 | Live panel/label toggles | §4.2 | Requirement recorded, mechanism undefined |
| 10 | Export-time clean/authoring scene config | §4.3 | Requirement recorded, mechanism undecided (Composer-strip vs Loader-suppress) |
| 11 | Scene/Story-Arc Library | §5 | Held — needs its own design pass |
| 12 | `DialogLine`/`Cue` schema, SQLite asset registry, text-hash drift detection | §5a | Designed, not built |
| 13 | "Chorus's characters" — unify live-riffed personas into the `emotionalInterpreter`/casting registry | §5a | **Not confirmed by author — do not build until confirmed** |
| 14 | Dialog-track "swap" UI → drag-to-align `audioOffset` | §5a | Noted for next mockup pass |

---

*Day 63: Spec written from the proto-library discussion (camera class generalization) and the trigger-system trace (current state confirmed by reading actual dispatch code, not assumed). New requirements captured: declared timeline triggers with audio duration/waveform support, expanded sensed triggers (depart, zone enter/exit), panel visibility and export-time clean/authoring scene modes, and a scene-level library for multi-scene emotional story arcs. Later same day: the SAI-into-proto risk (§2.2) was tested directly and resolved — proto internals are unreachable, exposed interfaces are required, PROTOs are decided as required infrastructure rather than an open direction. Naming conventions (§2a) added, motivated by the "SForw" trigger bug. Still later: Dialog & Voice Pipeline (§5a) added — then corrected same day: "Kate performs Anna" is casting for `emotionalInterpreter` (which LLM persona's accrued affective habits anchor a character's emotional range), not `voiceId` (audio rendering) — the two are separate fields. Interpreted affect is expressed as the same `ChannelVector` (E/B/P/S) already running live in `mccf_core.py`'s coherence/coupler engine, not a disconnected free-text tag. §1 gained a framing note tying this back to the system's stated purpose: a society-of-minds model of agent/node communications, tuned to produce coherence. One item in §5a explicitly flagged as not yet confirmed by the author. Everything else in this document remains unimplemented — see Camera System Spec v1.3 for the pattern this generalizes from, and §0 above for how to read the status markers in this doc.*
