# MCCF Actor Architecture — Design v0.2

*Day 71 design session, consolidated. Supersedes the per-path codegen model
diagnosed as broken on Day 70/71 (colliding DEF names, no orientation wiring,
dialogue coupled to waypoints). v0.2 folds in the trigger model, media/camera
track kinds, and declared-cue mechanics worked out while prototyping the
Timeline and Dialogue editors. This document does not specify code — it
specifies the shape code should take.*

---

## 1. Motivation

The current system generates bespoke, hand-numbered X3D nodes and scripts per
agent path (`Interp_<agent>_<seg>`, `Arrival_<agent>`, etc.), with a fresh JS
codegen function invoked per path and no shared naming authority across paths.
This produced real, confirmed bugs: DEF collisions between an agent's own takes,
arrival events misrouted to the wrong controller script, no avatar orientation
wiring at all, and dialogue text stored on waypoints rather than existing
independently.

Investigation of two legacy references — **Kamala** (`kamala01b.wrl`, a Blaxxun
Contact‑era avatar proto still runnable today, alongside Vivaty Editor — both
kept deliberately, not discarded, per the working rule that tech which still
runs is not obsolete) and **The River of Life** (`TheRiverofLife.x3d`, the ROL
scene that hosts her) — surfaced patterns worth keeping even though their
implementation predates X3D4 and is not portable:

- **Welder**: a single arbitration point that every gesture's per-joint
  interpolator output routes *through*, rather than directly onto the skeleton.
  Solves "which gesture owns this joint right now."
- **`Gstart`/`currG`/`nextG`**: an indexed dispatch pattern — starting a new
  gesture while one is active stops the old one and queues the new one, rather
  than stomping it.
- **`doAct`**: one script holding `USE`-references to nearly everything in the
  scene, acting as a single coordination point for triggers (touch, arrival,
  proximity) fanning out to camera cuts, dialogue, audio, and movement.
- **ROL's world composition**: geometry and avatars built once as
  `EXTERNPROTO`/`Inline` assets and referenced, never duplicated per scene.
- **ROL's chained-timer sound fades**: `FadeUpTimer.fraction_changed` driving
  intensity, chained off another event rather than a wall-clock guess — the
  origin of this design's push-based event model (§5.3), though see §3.1 for
  where that got over-generalized and had to be corrected.

The design below generalizes these patterns into one data-driven model instead
of Kamala/ROL's hand-authored one, guided by a single working principle:
**conserve nouns, conserve verbs.** Every category the system has to reason
about differently is a cost. This document holds the noun count at one and
the verb count at five — everything since, including cameras and media, has
had to fit inside that budget rather than growing it.

---

## 2. The one noun: Actor

Everything in a scene that *has behavior* — an avatar, a door, a fog volume, a
light, a sound zone fader, a music cue, a camera — is the same kind of thing:
an **Actor**.

An Actor is exactly three things:

1. **A field map** — which of its X3D fields the outside world (tracks, the
   emotion engine, other Actors) may read or write, and what each one means
2. **Tracks** — ordered sequences of steps the Actor can run
3. **A sub-coordinator** — arbitrates when more than one thing wants to write
   the same field at once. Only needed if the field map or track count creates
   contention; a single-track prop with no affect-writable fields needs no
   coordinator at all.

An avatar, a door, a music cue, and a camera are not different categories
under this model — see §7 for the camera case specifically, which turned out
to need no new noun at all, just a new track *kind* (§6).

**Zones remain a separate concept, deliberately.** A Zone is a spatial trigger
source — it fires events *into* Actors — but it has no field map and no tracks
of its own. Collapsing Zones into Actors would blur "the thing that fires the
verb" with "the thing that receives it," which is exactly the distinction
worth keeping.

**Authoring-time exception, not a data-model exception:** the Scene Composer
UI may present Actor creation through templates (Avatar, Prop, Ambient Cue,
Camera) that pre-fill sensible field maps and track shapes. This is a
convenience layer for the human, not a second runtime noun — an exported
Actor is always just `{fields, tracks, coordinator}` regardless of which
template built it.

---

## 3. The five verbs

| Verb | Direction | Meaning |
|---|---|---|
| `start` | into an Actor | Begin a track, or the next queued step in one |
| `stop` | into an Actor | Halt whatever's currently running on a track |
| `arrived` | out of an Actor | A step completed on its own (Timer done, TTS done, waypoint reached, door finished swinging) |
| `blocked` | out of an Actor | A step could not complete (collision, missing asset, sensor never fired) |
| `set` | into an Actor's field map | Direct value write, bypassing tracks entirely |

`start`/`stop`/`arrived` generalize Kamala's `Gstart`/`Gend` past gestures to
every Actor type. `blocked` is new — Kamala's system had no clean way to say
"this didn't work," which is part of why arc/take failures were hard to
diagnose; giving it a name means a track step can fail loudly instead of
silently. `set` names what `HotHouseX3DAdapter` and the ROL sound-fader ramps
were already doing (writing `color_Alice`, `visibility`, gain values directly)
as a first-class verb instead of an ad hoc path.

No other verbs. A camera cut, a dialogue line, a waypoint arrival, an
explosion, and a door opening are all just `start`/`arrived`/`stop`/`blocked`
against different Actors — the vocabulary doesn't grow per Actor type or per
trigger source.

### 3.1 Triggers: declared vs. sensed

Every step's `start` is caused by something. That something is a **trigger**,
and it comes in exactly two flavors:

| Trigger type | Fires when | Example |
|---|---|---|
| `scene-start` | Playback begins | An avatar's first path segment |
| `touch` | A TouchSensor fires | A door opens on contact |
| `zone` | An avatar enters a named Zone | Dialogue keyed to spatial arrival |
| `sensed` | Another step reports `arrived` | A path segment chaining to the next |
| `declared` | The master clock reaches a specific time | A scored music cue, a scripted event at T=58s |

**Correction on record:** an earlier pass through this design (mid-session)
generalized "event-driven, not clock-driven" from a ROL-specific workaround
(ROL had no global clock, so Kamala's `doAct` had to chain everything off
sensed events) into a rule for MCCF, which does have a master clock and
doesn't need that workaround. `declared` triggers are not a compromise or a
fallback — given a real clock, they are the *simpler* mechanism: deterministic,
independent of any avatar's actual pacing, and exactly what an author reaches
for first when timing a beat ("the ground shakes at T=58s") rather than
inferring it from spatial state. Both trigger families coexist on the same
timeline, on the same Actor, sometimes on the same track — trigger type is a
per-step choice, not a scene-wide policy.

`zone` and `touch` are themselves sensed triggers with their own event
sources (a ProximitySensor, a TouchSensor); they're broken out from generic
`sensed` because they don't reference another step's `arrived`, they reference
a spatial/interaction event directly.

### 3.2 Duration certainty: fixed vs. estimate

Orthogonal to trigger type, every step also declares whether its *duration*
is known:

- **`fixed`** — computable at export time (a path segment's `distance/pace`
  travel time, an authored static dialogue line, a music file's real length,
  a movie clip's real length, a scripted gesture's baked animation length).
- **`estimate`** — genuinely unknown until runtime (an improv dialogue line
  generated live via ollama and spoken via TTS; `arrived` still fires when
  TTS finishes, but nothing can promise in advance how long that will take).

These two axes are independent: a path segment is typically `sensed` +
`fixed`; an improv line is typically `sensed` + `estimate`; a scored music cue
is typically `declared` + `fixed`; a declared cue's gesture response is
`declared` + `fixed`. All four combinations are legitimate. A timeline
authoring surface should render both distinctly (see §8) rather than treating
"has a time position" and "that position is guaranteed" as the same claim.

---

## 4. Field maps

Every Actor type ships a manifest describing its exposed fields. This is the
layer that makes the emotion engine able to "touch anything that exposes the
right field" without being a secret sauce — it's kept in XML and the API
layer. The engine never needs proto-specific knowledge; it asks "does this
Actor expose channel X," and if yes, writes to whatever field is mapped to it.

### 4.1 Manifest shape

```
Actor type: <name>

field: <x3d field name>
  reach:        track-only | affect-writable | telemetry
  channel:      <emotional channel this field responds to, if affect-writable>
  curve:        <direct | inverse | custom, if affect-writable>
  range:        <min – max, in the field's native units>
  arbitration:  replace | blend | track-wins   (only if both track- and
                                                 affect-writable)
```

- **`track-only`** — a track may write it; nothing else may. (e.g. a door's
  `hingeAngle`, driven only by its own open/close track.)
- **`affect-writable`** — the emotion engine (or any other Actor's
  coordination logic) may write it via `set`, subject to the arbitration rule
  if a track also claims the field.
- **`telemetry`** — read-only outward. Nothing writes it externally; it exists
  so other systems (a coordinator, a UI, a log) can observe state (e.g.
  `translation` on an avatar).

**A field map with zero entries is a legal, honest declaration** — it means
"this Actor is narrative-inert, tracks-only, not affect-reachable." An Actor
with *no manifest at all* is not legal to export. The manifest is a required
artifact, even if empty, so field exposure is always a decision on record
rather than an accident of what someone happened to wire.

### 4.2 Worked manifests

**Avatar (Kamala-class):**

```
Actor type: Avatar

field: idleGestureBias
  reach:        affect-writable
  channel:      arousal
  curve:        direct
  range:        calm(0.0) – wary(1.0)
  arbitration:  track-wins   # only meaningful while idle; a running
                              # gesture track owns the skeleton outright

field: walkPace
  reach:        affect-writable
  channel:      arousal
  curve:        direct
  range:        0.9 – 1.6 (m/s)
  arbitration:  blend         # affect nudges the recorded pace, doesn't replace it

field: poemLine / dialogueText
  reach:        track-only    # owned by the dialogue track; not affect-writable
  range:        n/a

field: translation
  reach:        telemetry
  range:        n/a
```

**Prop — SceneFog (autonomous by default, opted into affect):**

```
Actor type: SceneFog

field: visibility
  reach:        affect-writable
  channel:      tension
  curve:        inverse       # higher tension -> lower visibility
  range:        2000 – 80
  arbitration:  replace        # no competing track; nothing else claims it

field: color
  reach:        affect-writable
  channel:      valence
  curve:        custom         # warm ochre -> cold blue-grey, not a scalar lerp
  range:        n/a
  arbitration:  replace

field: cycleInterval
  reach:        track-only     # day/night cycle; not narrative-reachable
```

**Prop — Door (mostly inert, one small hook):**

```
Actor type: Door

field: hingeAngle
  reach:        track-only

field: swingSpeed
  reach:        affect-writable
  channel:      tension
  curve:        direct
  range:        0.6x – 1.3x nominal
  arbitration:  blend
```

**A note on field-map conflicts (observed, not yet resolved as policy):**
prototyping surfaced a real case where two `set` steps target the same field
on the same Actor — an ongoing tension-driven fog coupling and a sharp
declared-cue flicker spike both writing `visibility`. The `arbitration`
column says *how* a track and affect resolve against each other, but doesn't
yet say how two *simultaneous affect-writers* resolve against each other.
Carried to §9 as open.

---

## 5. Sub-coordinators

Every Actor with more than one track, or with any affect-writable field that a
track also touches, needs a sub-coordinator. Its job is narrow on purpose: **it
decides who currently owns each contested field**, nothing more. Scene-wide
sequencing (what happens after what, across Actors) does not live here — see
§8.

### 5.1 The Welder pattern, generalized

Kamala's Welder is a single-track-at-a-time arbitrator scoped to one Actor's
entire skeleton: starting a new gesture always displaces the current one. That
is the *default* arbitration policy for any Actor with multiple tracks that
can't sensibly run concurrently.

**This policy generalizes further than gestures.** A camera cut has the exact
same shape — X3D only ever binds one `Viewpoint` at a time, so "the next cut
displaces the previous" is Welder's policy applied to a Camera Actor's `cuts`
track, with no new arbitration mechanism required (§7). Two independently
discovered cases (gesture, camera) landing on the same default policy is a
reasonable signal that it's the right default, not something scoped narrowly
to skeletal animation.

It is **not** assumed to generalize automatically to "one arbitrator per
Actor" in every case. Where an Actor has fields that genuinely don't contend
(a door's `hingeAngle` and an independent `creakVolume`), those fields don't
need to share an arbitrator at all — the coordinator can be as simple as
"each field has at most one writer at a time," checked per field, not
per Actor. Building a joint-group-level arbitrator (upper body gesture
concurrent with a walk-cycle track) is explicitly **not** in scope yet — flag
it as a known future need, not a current requirement. Kamala ran a real
production for years on the simpler one-owner-at-a-time model.

### 5.2 Arbitration when a track and the affect engine both claim a field

This is the situation the field map's `arbitration` column resolves, decided
per field, not globally:

- **`replace`** — affect's `set` wins outright while active; no track
  currently claims this field, or the Actor's design intends affect to simply
  override it (e.g., ambient fog with no competing track).
- **`blend`** — the sub-coordinator combines the track's value and the
  affect-written value (e.g., `walkPace` = recorded pace × arousal
  multiplier). The blend function is Actor-type-specific, but *that a blend
  happens at all* is declared in the manifest, not buried in code.
- **`track-wins`** — a running track's value is authoritative; affect's `set`
  is only honored when the Actor is otherwise idle (e.g., `idleGestureBias`
  only matters between gestures, never during one).

### 5.3 Push, not pull

Consistent with X3D's native ROUTE/event model and the River of Life
sound-fader precedent, sub-coordinators are **pushed to**: a top-level
dispatch calls `start`/`stop`/`set` on an Actor; the Actor pushes
`arrived`/`blocked` back out when something changes. Nothing polls a shared
schedule — this holds for `declared` triggers too: the master clock pushes a
`start` at the authored time, it doesn't get polled for by each Actor.

### 5.4 Declared cues vs. a running track: the collision case

A `declared` trigger can land on a field or track that's already active — a
scored explosion at T=58s while an avatar's improv line is still playing.
This is new territory, distinct from §5.2 (that's track vs. affect; this is
clock vs. track), and it needs its own per-step policy rather than a global
rule:

- **`interrupt`** — the declared step cuts off whatever's running and takes
  over immediately. Right default for a sudden physical event (a startle
  gesture, a door slamming).
- **`wait`** — the declared step holds until the running thing finishes, then
  fires. Right default for a scored music cue that shouldn't clip dialogue.
- **`overlap`** — both run concurrently (only sensible where the two don't
  actually contend on the same field — e.g. a sound effect declared alongside
  an ongoing ambient bed).

Like `arbitration` in §5.2, this is authored per step, not assumed globally.

---

## 6. Track kinds

A track has a `kind`, which determines how its steps render and what
Actor-specific fields a step carries — but never adds a new verb or a new
noun. Kinds identified so far:

| Kind | Carries | Example |
|---|---|---|
| `path` | position/orientation keys | An avatar's walk |
| `gesture` | skeletal animation reference | Idle sway, a startle |
| `dialogue` | line content, voice, TTS params, blocking flag | A spoken line |
| `affect` | field + channel (an Actor exposing itself to the emotion engine) | Fog visibility coupling |
| `prop` | Actor-specific mechanical fields | A door's swing |
| `audio` | clip reference, real duration, gain | Ambient bed, music, SFX |
| `movie` | clip reference, real duration | A `MovieTexture` overlay |
| `camera` | camera type + target (§7) | A cut, an orbit, a dolly |

`audio` and `movie` didn't need a new noun either — X3D's `AudioClip` and
`MovieTexture` already have native `start`/`stop`/`loop` semantics, and both
have (or can have) a `duration_changed`-style output, which is exactly what
`arrived` should hang off for `fixed`-duration media. Multiple simultaneous
`audio` tracks (ambient bed, music, dialogue, SFX) are just multiple tracks
of that kind on whichever Actor owns them — a scene-level "Score" Actor for
music, each Zone's ambient bed as its own track, dialogue staying where it
already is (per-speaking-Actor).

---

## 7. Camera as an Actor

Cameras are a `Camera`-type Actor with a `cuts` track (kind `camera`), no
new mechanism required — this is the same shape as everything else, and it
validates §5.1's generalized Welder policy rather than needing its own.

Each `camera`-kind step declares a `cameraType`, selectable per step:

| Type | Needs | Maps to (existing precedent) |
|---|---|---|
| `fixed` | a named viewpoint | `VP_Overview`, per-zone `VP_<id>` |
| `orbit` | a target Actor | `AgentOrbitCamera` proto |
| `track` | a target Actor | `AgentTrackCamera` proto |
| `pov` | a target Actor | Kamala's `KamalaView`/`KamalaView2` |
| `dolly` | (none) | Kamala's `Moving_Viewpoint` + keyframed path |

A camera cut can be `sensed` (cut when an avatar enters a zone) or `declared`
(cut at a scored beat) exactly like any other step, and can be part of a
multi-Actor declared cue (§8) alongside lights, sound, and gesture — a hard
cut to a tight orbit is a legitimate response to the same clock trigger that
also fires a startle gesture and a door slam.

**Open, not resolved:** no `stop`/release verb is specified for cameras yet —
the displacement policy (§5.1) means a new cut always overrides the old one,
but there's no way to say "release back to whatever was bound before this,"
which a real authoring flow will likely want. Carried to §9.

---

## 8. Scene-level coordination

Sub-coordinators arbitrate *within* one Actor. Something still needs to
sequence *across* Actors — Cindy's coupling with Jack, a camera cut timed to
a dialogue line's end, a Zone's proximity trigger firing into two different
Actors at once (River of Life's `FollowKamala` touch firing `setCamera`,
`selectPoem`, and `setFollowKamala` simultaneously is the precedent for this
fan-out), or a single declared clock trigger fanning out to several Actors at
once (§8.1).

This is a single scene-level dispatcher, generic across every Actor — it does
not grow bespoke fields per scene the way `doAct` did
(`walkToRosePosition`, `setCamForMarbleJar`, ...). It only ever speaks the five
verbs against whichever Actor a track/zone/cue names as its target. Coupling
logic (the emotion engine reading every Actor's telemetry, computing channel
values, issuing `set` calls) lives at this level too — it is scene-wide by
nature, not owned by any single Actor's sub-coordinator.

### 8.1 The master clock and declared multi-Actor cues

A scene has one master clock, real seconds, that every `declared` trigger is
authored against. An author can name a **cue** — a single declared moment
("Ground tremor," T=58s) — and attach a response step on any number of
Actors to it in one action: a gesture on an avatar, a `set` write on a prop's
field, a sound effect, a camera cut, all sharing the same trigger time and
cue name. This is the direct generalization of `FollowKamala`'s three-field
fan-out, now driven by a clock tick instead of a touch, and available to any
combination of Actors rather than one hand-wired script.

### 8.2 Timeline representation

Because `fixed`- and `estimate`-duration steps make genuinely different
promises (§3.2), a timeline authoring surface needs a ruler in real seconds
(not a fixed-total-duration fraction) that:

- **Extends in X** as far as the furthest-placed step (declared or estimated)
  requires — never a pre-guessed total scene length.
- **Extends in Y** with actor/track count, lazily rendered once that count
  gets large.
- Visually distinguishes **trigger type** (declared vs. sensed — e.g. solid
  vs. dashed border) from **duration certainty** (fixed vs. estimate — e.g.
  solid vs. hatched fill) as two independent properties on the same step,
  not one collapsed distinction.
- Shows declared multi-Actor cues (§8.1) as a visible cross-lane marker, so
  the fan-out is legible at a glance rather than only inferable per-step.
- Surfaces `blocked` steps visibly (a persistent, distinct visual state) —
  failures should be as visible as successes, which nothing in the prior
  system did.

---

## 9. Worked example: the descent into the underworld

A scene-level `tension` channel (0→1) rises as the avatar walks from the
garden zone into the underworld zone. Nothing here needs a track, a Zone
trigger beyond the initial zone-entry event, or new coordinator logic — it is
five `set` writes into five field maps, driven by one scalar:

| Actor | Field | Channel | Effect as tension → 1 |
|---|---|---|---|
| SceneFog | `visibility` | tension (inverse) | Fog closes in |
| Directional light / `Background.skyColor` | `color` | valence | Warm ochre → cold blue-grey |
| Ambient sound bed | gain (ROL-style fader) | tension | Crossfades in the dread bed |
| Avatar | `idleGestureBias` | arousal | Idle timer favors wary gestures over relaxed ones |
| Avatar | `walkPace` | arousal | Footsteps quicken, blended with recorded pace |

Layered on top of that continuous coupling, a single **declared** cue —
"Ground tremor," T=58s — demonstrates §8.1's fan-out concretely: a startle
gesture on the avatar, a flicker spike on `SceneFog.visibility` (landing on
top of the continuous tension coupling above — the unresolved multi-writer
case from §4.2), the temple door slamming shut, a stone-groan sound effect,
a portal-ripple movie overlay, and a hard camera cut to a tight orbit — six
Actors, one clock trigger, each with its own `onCollision` policy (§5.4).

This is the payoff of §4 and §8.1 together: escalating dread is one number
reaching into five manifests; a scripted beat is one clock tick reaching into
six Actors. Neither needed a new noun or a new verb.

---

## 10. What this replaces, concretely

- Per-path `Interp_<agent>_<seg>` / `Timer_<agent>_<seg>` / `Arrival_<agent>`
  codegen → one continuous position+orientation interpolator pair per Actor
  per scene, baked at export time from the Actor's path track.
- `waypointOrder` / multi-`Arrival_` staging / `advanceSeg` wiring → scene-
  level dispatcher pushing `start`/`arrived` against Actors; no per-path
  script state to go stale.
- Dialogue-on-waypoint → dialogue is its own track on the Avatar Actor,
  triggered by (not stored inside) a spatial `arrived` event, or by a
  `declared` trigger, or by any other event in the scene.
- `SoundFader`'s `playing` gate → an ordinary `affect-writable` field
  (or track-only, if it should stay purely proximity-driven) on a SceneFog/
  SoundZone-class Actor, declared in its field map instead of implied by a
  script guard nobody routes to.
- `doAct`'s hand-wired, per-scene bespoke fields (`walkToRosePosition`,
  `setCamForMarbleJar`, ...) → the generic five-verb dispatcher (§8), with
  camera cuts as an ordinary Actor/track rather than a special case.
- The `MCCF_Bridge` script's hardcoded `scale_<agent>`/`color_<agent>`
  fields in `export_x3d()` → the same field-map lookup (§4) driving every
  `set`, so there's one affect-bridge mechanism instead of two parallel ones.

---

## 11. Prototypes built against this design

Two interactive HTML prototypes exist as reference implementations, not
production code:

- **Timeline editor** — one lane per Actor track, a real-seconds ruler and
  scrubber, a declared-cue builder (name a cue, attach responses across
  multiple Actors/tracks/verbs in one action), a step inspector showing
  verb/trigger/duration-certainty/field-map/arbitration/collision-policy per
  step, audio tracks rendered as waveform blocks, movie tracks as filmstrip
  blocks, camera cuts with a selectable camera type, and a blocked-step
  visual state.
- **Dialogue editor** — one Actor's dialogue track as an ordered list; each
  line's trigger is chosen from *any* event in the scene (zone entry, touch,
  another track's `arrived`, a declared time), not tied to a waypoint;
  static/improv is an explicit toggle with the improv case explaining that
  duration is a runtime estimate; blocking is an explicit per-line flag.

Both include an honest "not wired to the API" flag and a stubbed, clearly
non-functional preview pane reserving space for the screen-capture-to-mp4,
scrubber-synced playback workflow described for future authoring (watch a
recorded run, drop new declared cues at the moment something on screen calls
for one — DAW-style hit-pointing).

---

## 12. Open items, carried forward rather than resolved here

- Field-map schema needs a concrete serialization (JSON alongside each Actor
  type's proto, or inline in the proto's `ProtoInterface` as metadata) —
  next artifact after this one.
- Blend functions for `arbitration: blend` fields are Actor-type-specific and
  unspecified here — first candidates are `walkPace` and `swingSpeed`.
- Joint-group-level pose arbitration (concurrent upper/lower body tracks) is
  out of scope; revisit if a scene actually needs walk-and-gesture
  concurrency.
- **Two simultaneous affect-writers on the same field** (§4.2) — the
  `arbitration` column resolves track-vs-affect, not affect-vs-affect. Needs
  a policy (priority order? most-recent-write-wins? scene-level exclusivity
  per field?) before the Ground Tremor worked example's fog conflict is
  actually resolved rather than just flagged.
- **Camera release/stop** (§7) — no way yet to say "return to whatever was
  bound before this cut" rather than always cutting forward.
- Whether affect ever writes ambient/autonomous Actors that currently need no
  field map at all (shooting stars, day/night cycle) stays a per-Actor
  decision — the test remains: *does anything external ever need to trigger
  it, or does it ever contend with another track for the same field?* If no
  to both, no manifest entry is needed for that field, and the Actor may ship
  with a deliberately empty or near-empty map.
- Real waveform rendering (Web Audio `decodeAudioData` → peaks → canvas) is a
  separate subsystem from the Actor/track model and doesn't depend on it —
  worth prototyping in isolation rather than inside the timeline editor.
- The screen-capture/mp4 preview pane (§11) is authoring tooling, not
  runtime architecture — deliberately left undesigned until the rest of this
  is stable.
