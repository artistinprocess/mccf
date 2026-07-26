# MCCF V5 Integration — Nominal Edit Order & Task List v0.1

*Day 78. Companion to `MCCF_Camera_Model_Revision_v0.1.md` (camera work,
V4-phase) and the three Day 75/76 specs
(`MCCF_Scene_Integration_Spec_v0.1.md`,
`MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md`,
`MCCF_Lighting_System_Spec_v0.1_DRAFT.md`). Written after re-confirming
the Actor model with the author directly and researching X3D's Followers
component and Spline interpolators against real, current X_ITE
documentation — not from memory. Marks clearly what's firm (confirmed by
code, spec, or direct author statement) versus proposed (this doc's own
synthesis, needing confirmation) throughout.*

---

## 1. The Actor model — now sourced from the actual Day 71 design doc, not reconstructed

**Precise definition, `MCCF_Actor_Architecture_Design_v0.2.md` §2 — the
authoritative source, read in full Day 78, superseding this doc's
earlier conversation-search reconstruction:** an Actor is exactly three
things — **a field map** (which fields the outside world may read/write,
and what each means), **tracks** (ordered step sequences the Actor can
run), and **a sub-coordinator** (arbitrates contested-field ownership;
needed only where real contention exists — a single-track prop with no
affect-writable fields needs none at all). *"Conserve nouns, conserve
verbs"* is the doc's own stated organizing principle — one noun (Actor),
five verbs (§3 below), and every later addition (cameras, media) had to
fit inside that budget rather than growing it.

The author's own summary — *"an actor is any animated object in a
scene... an avatar has behaviors baked in and can be triggered by any of
the trigger classes"* — is a correct, compressed restatement of this,
confirmed against the source rather than left as a paraphrase.

**A real correction, not just imprecision:** the earlier reconstruction
never explicitly excluded Zones from the Actor concept, and it should
have. *"Zones remain a separate concept, deliberately. A Zone is a
spatial trigger source — it fires events into Actors — but it has no
field map and no tracks of its own. Collapsing Zones into Actors would
blur 'the thing that fires the verb' with 'the thing that receives
it.'"* `zones{}` stays permanently separate from any Actor
reconciliation, on the design's own authority, not by omission.

**Validates the Phase 1 recommendation more strongly than originally
claimed.** §6's earlier analysis recommended reconciling at the export
boundary rather than restructuring `placedAgents`, based on risk-
avoidance and the Timeline prototype's own precedent. The design doc
goes further — this is the *intended* shape, not just a safe
implementation choice: *"the Scene Composer UI may present Actor
creation through templates (Avatar, Prop, Ambient Cue, Camera)... This
is a convenience layer for the human, not a second runtime noun — an
exported Actor is always just `{fields, tracks, coordinator}` regardless
of which template built it."* Composer staying organized by
`placedAgents`/`placedCameras`/`zones` isn't a compromise against the
design; it's what the design itself asked for.

**One genuinely new, real gap surfaced by reading this doc, not
previously on this list:** camera release/stop. *"No `stop`/release verb
is specified for cameras yet — the displacement policy means a new cut
always overrides the old one, but there's no way to say 'release back to
whatever was bound before this,' which a real authoring flow will likely
want."* Explicitly flagged as open in the original design (§7, carried
to §12) and not resolved anywhere seen since — added to Phase 4's task
list below.

**Confirmed resolved since this doc was written:** the affect-vs-affect
same-field conflict this doc's own §12 leaves open (the Ground Tremor
fog case) — `dispatcher.js`'s comments explicitly record the decision
("declared write locks the field for its step's duration; continuous
writes are refused, not queued, while the lock holds") as made *because*
of this exact open item. Clean chain of custody: open question here →
resolved decision on record in the actual working code.

**Confirmed still open, corroborated rather than newly found:** blend
functions beyond `walkPace`/`swingSpeed` — this doc names them as the
*first candidates* (§12), `dispatcher.js`'s `BLEND_FUNCTIONS` confirms
only those two ever got real functions defined; joint-group-level pose
arbitration (concurrent upper/lower body tracks) — explicitly out of
scope by design, not a gap to close, *"Kamala ran a real production for
years on the simpler one-owner-at-a-time model."*

**Still genuinely open, unchanged:** whether `mccf_scene_composer.html`'s
own in-memory `placedAgents` object needs any restructuring at all, given
the "convenience layer, not a second runtime noun" framing above — or
whether the export-boundary adapter is sufficient on its own with zero
changes to `placedAgents` itself. Leaning further toward "zero changes
needed" after reading this doc, but not yet confirmed as a final answer.

## 2. Dialogue leaves the Waypoint

**Firm, author-stated.** *"Dialogues are not limited to the WPs so the
Waypoint definition does not include the dialogs as per current
version."* Real migration implication: the Waypoint data model currently
*carries* dialogue (`wp.question`/`wp.qaLines`, read directly by
`_sceneArcAdvance` — confirmed in `mccf_scene_composer.html`). Under the
new model, Waypoint drops that content entirely; the Timeline/Dialogue
editor's own Track/Step/Line structure becomes sole authority.

**Update, Day 78, all five Timeline-tool JS files now read in full:**
this migration isn't a design gap anymore — it's already solved, in
real, working code. `dialogue-xml.js`'s `parseLegacyWaypointLines()`
pulls `Question`/`Response`/`Statement` lines straight out of
`<Waypoint>` elements and converts them into the new `<Dialogue>`
format, tagged with a first-class `legacy-waypoint:<name>` trigger type
— `TRIGGER_KINDS` includes it alongside `scene-start`/`touch`/`zone`/
`sensed`/`declared`/`arc-complete`. The schema was built anticipating
this exact transition; there's no "clean cutover vs. transition period"
decision left to make — the migration tool already exists and already
round-trips.

## 3. Construction order — the real fix is refresh-on-focus, not just a fixed tab order

**Firm, already built and proven this session, just narrowly.** The
problem as the author described it: *"the agents have to be in the
scene [before Timeline/Dialogue authoring], so the author has to do it
out of order and the dialog and timeline editors cannot pull from the
objects in memory."* This session fixed exactly this class of problem
for the old events editor's scene-data bridge — a module that only
pulled a snapshot once (on tab-open or iframe-load) missed anything
added to the scene afterward. The fix wasn't "pick a better order," it
was: **any module that references Actors re-pulls a fresh snapshot every
time it gains focus**, not just once. That's the mechanism that actually
solves the "author jumps around non-linearly" case — a good default tab
order helps the common case, but only live refresh-on-focus survives an
author editing an agent *after* the Timeline tab is already open with
stale dropdowns. Proposed: extend the same pattern
(`_sendSceneDataToEventsEditor`'s force-refresh-on-open, cues cached and
re-sent) to whatever bridge the Timeline/Dialogue editor ends up using,
rather than re-deriving it.

## 4. Record Arc — examined directly, confirms the stated limitation exactly

**Firm, read from source, not assumed.** `_sceneArcAdvance` in
`mccf_scene_composer.html`:

```js
var pos = wp.position || [0,0,0];   // plain [x,y,z] point, nothing else
var pace = 2;  // recording step interval (s) — X3D timers drive actual movement timing
```

Recording steps through waypoints at a fixed interval; it doesn't
simulate movement at all. Playback (today's `PositionInterpolator`
system) draws a straight line between two such points. Orientation is
never authored — it's *derived* at playback time from the vector between
two waypoints (`_pivotAgentToSegment` computing heading from `dx`/`dz`,
confirmed in live console logs earlier this session). No curve, no
elevation change, no independent orientation, no obstacle-awareness
anywhere in the chain. The author's diagnosis was exact.

## 5. The path recorder — Blaxxun-style capture, researched against real X_ITE docs

**Firm on the concept, author-confirmed:** an author sets fly-mode
navigation, flies the path they want (curves, elevation, obstacle
avoidance), and the system captures position/orientation as they go —
*"essentially, capture and name a path... that means the path exists
independently and can be used by any moving object in the scene."*

**Confirmed correct, mechanically, by re-checking a fact established
earlier this session:** ordinary `ProximitySensor` only ever reports the
*bound viewpoint's* position, never an arbitrary object's. This design
works precisely *because* it's the author's own navigation camera being
tracked during authoring — the author's viewpoint genuinely is what's
bound during that flight. This would not work for capturing an
arbitrary AI-driven avatar's position at runtime; that's a different,
unrelated mechanism (routing the avatar's own Transform fields
directly) and isn't what this is for.

**Researched, not assumed — the two native X3D tools this need actually
maps onto, and they're different tools for different sub-problems:**

- **Path *playback*** (the actual captured/thinned/named path,
  used by any object) → `SplinePositionInterpolator` +
  `SquadOrientationInterpolator`. Confirmed supported in X_ITE (Followers
  overview page). Structurally identical to the `TimeSensor`/
  `Interpolator`/`ROUTE` chain already proven throughout this codebase —
  the only change is swapping linear interpolators for spline ones.
  `SplinePositionInterpolator` has a `keyVelocity` field per keyframe,
  directly useful for a path that has to bend sharply around an obstacle
  versus one that sweeps a gentle arc.
- **Live reactive following of a *changing* target** (not what path
  recording needs, but a genuinely useful *other* capability worth
  scoping separately) → `PositionChaser`/`PositionDamper` and their
  `Orientation` counterparts. Confirmed field semantics directly from
  the X3D spec text: `set_destination` in, `value_changed` out; Chaser
  uses a fixed `duration` and settles with a spring-like, slightly
  overshooting character; Damper uses `tau` (an exponential-decay time
  constant) plus `order` (0–5 smoothing) and `tolerance` (when to
  consider "arrived"), and never truly reaches the target — it just gets
  asymptotically close, which is the point. **This reframes something
  built earlier this session:** `agent_track` currently bakes fixed
  keyframes at export time. A `PositionDamper`/`OrientationDamper` pair,
  routed live from the subject's own Transform, would be a more honest
  implementation of "camera tracks a moving subject" — reactive, not
  pre-baked. Worth a real reconsideration, not just an addition, once
  bandwidth allows — not blocking anything else in this doc.

**Author-flagged, not yet designed:** thinning/decimation. A live-flown
capture at browser frame rate would produce a huge, unusable keyframe
list. Needs a real decimation strategy (distance/angle-threshold-based
keyframe reduction is the obvious first approach — drop a captured
sample unless it deviates from the current trend by more than some
tolerance) before baking into Spline interpolator keys. Not designed in
this doc.

**Proposed, needs confirmation, not yet decided:** the author raised
*"possibly because we have the old events editor X-Ite preview, we
could add a path recorder there."* Worth flagging a real tension: the
Scene Integration Spec says this exact preview is being retired
(*"caused tab crashes, the grid editor was not very functional"*) — but
this session already found and fixed the two specific root causes of
that instability (the `getField().setValue()` SAI bug, and the
refresh-button teardown leak). The preview is in better shape now than
when it was flagged for retirement. That doesn't settle whether it's
the right *home* for a path recorder — a narrowly-purposed new tool
built for this one job might still be cleaner than reviving a general
preview surface for a different purpose — but it does mean "it used to
crash" is no longer a strong argument against reusing it. Real decision,
not made here.

**Also proposed, needs confirmation:** a recorded path becomes a new,
independent composer entity — not owned by one agent the way `paths{}`
currently is (`path.agent`). Binding a specific object to a specific
named path becomes a separate step (setting up the `ROUTE`s from the
path's interpolators to that object's `Transform`), and the same named
path could plausibly drive more than one object, or the same object
along different paths at different times. This is real new data-model
surface, not an extension of the existing `paths{}` structure.

## 5a. Record Arc, actually read end to end this session — three real findings

**Firm — recording-side grouping is structurally safe from the exact bug
fixed in playback earlier this session.** `_groupPathsByOrder` and every
downstream state tracker (`_sceneArc[pn]`, `st.path`) are keyed by *path
name*, never agent/cultivar name. The playback bug this session found
and fixed was specifically an agent-name-keyed collision when one agent
has multiple paths — recording was never built that way, so it doesn't
share the bug. Confirmed by reading the code, not inferred from the fix
elsewhere.

**Firm — a second, separate instance of the "SAI-set coordinates"
anti-pattern the author flagged, distinct from anything fixed today.**
`mccf_x3d_loader.html`'s `applyArcCV()` — the function that visually
represents movement *during Record Arc's own live preview* while
dialogue is being captured — does exactly this:
```js
avatarNode.translation = new X3D.SFVec3f(x, 0, z);
```
A raw snap-to-point on every ~2-second recording tick, Y hardcoded to
zero even if a waypoint's own position carries elevation. This is
*separate* from actual scene playback (which correctly uses `TimeSensor`/
`Interpolator` since today's earlier fixes) — it's specifically Record
Arc's own preview-while-recording path, never touched today. Real
open question: does the new curved-path/interpolator system need to
extend into Record Arc's live preview too, or is snap-to-point
acceptable there specifically, since it's a rough "where are we now"
indicator for the author while capturing dialogue, not the final
production output any end viewer sees? Genuinely don't know your intent
here — flagging precisely rather than assuming either way.

**Firm — the arc XML round-trip (`_saveSceneArc` → `/arc/export` in
`mccf_api.py` → `parse_arc_file` in `mccf_playback.py`) is clean and
consistent.** `pos_x`/`pos_y`/`pos_z` attributes match exactly on both
ends. No hidden format mismatch to design around.

**Firm — the path-recorder's proposed capture mechanism needs one
correction, found by checking the X3D spec directly rather than
assuming the author's `ProximitySensor` framing was the only option.**
The spec is explicit that the browser moves the *bound Viewpoint node's
own* `position`/`orientation` fields as the user navigates — meaning a
`ProximitySensor` isn't the only way to read that stream; `addFieldCallback`
directly on the bound Viewpoint's own fields works too, and does **not**
share `ProximitySensor`'s real limitation: **the existing "scene zone"
(`Prox_The_Ialand`, confirmed from a real scene: `size="80 4 80"`) is
only 4 meters tall.** An author flying up for a crane-height shot —
explicitly named as a goal — would exit that box almost immediately and
capture would silently stop. Direct Viewpoint-field polling has no such
bound. Given the stated goal (elevation, terrain, genuinely free flight),
I'd lean toward recommending the direct-field approach over the
`ProximitySensor` one, but this is your call to confirm, not something
I should just decide and move on from.

## 6. All five remaining questions settled, Day 78

**1. Actor/`placedAgents` — reconcile only at the generator/export
boundary, not a full restructure.** Full advantages/disadvantages
analysis:

*Restructure (`placedAgents` → general `placedActors`)* — advantages:
true internal consistency, no translation layer, new Actor types built
once generically, Timeline editor and composer speak the same language
natively. Disadvantages: `placedAgents` is touched dozens of times
across `buildAX3D`, the Agents tab, the Character Creator bridge, and —
critically — today's entire camera-rig-manifest work
(`camRigFetchManifest`, `_camRigManifestCache`, `buildAX3D`'s IMPORT-
gating logic) lives directly inside it. Real regression risk against
just-stabilized code, for a benefit that's achievable another way.

*Reconcile at the boundary (kept separate, thin export-time adapter)* —
advantages: minimal risk to working code, each authoring UI stays
optimized for its own job, and **this isn't speculative — it's already
the proven pattern in this exact codebase**: the Timeline prototype's
`REAL_MANIFEST_TYPES`/`MANIFEST_BY_TYPE` does exactly this, tested in
Node before being placed into the browser tool. Disadvantages: the
adapter needs active maintenance as new Actor types are added — two
places touched instead of one, with a testable but real risk of drift.

**Decided: reconcile at the boundary.** Not because it's more elegant —
it isn't — but because the lower-risk path is already validated in
tested code, and a full restructure right now would put today's
freshly-stabilized camera work at unnecessary risk for a benefit a thin
adapter delivers just as functionally. Revisit as a full restructure
later if the Actor-type roster grows enough that the adapter itself
becomes the awkward part.

**2. Path-recorder capture mechanism: direct Viewpoint-field polling.**
Confirmed — avoids `ProximitySensor`'s real limitation (the existing
scene zone is only 4m tall; an author flying up for a crane shot would
silently exit it and lose capture). `addFieldCallback` on the bound
Viewpoint's own `position`/`orientation` fields has no such bound.

**3. Record Arc's own live preview stays rough (snap-to-point),
`applyArcCV` not touched for smoothness.** One real, low-risk fix
identified and worth doing regardless of this decision:
`applyArcCV` hardcodes `pos_y: '0.00'` even when a waypoint's own
position carries elevation — a one-line correctness bug
(`pos[1].toFixed(2)` instead of the hardcoded zero), independent of
whether the preview ever gets proper interpolation. Small task, not
blocking anything, not yet done.

**4. Decimation: Ramer-Douglas-Peucker, not a distance/angle streaming
threshold.** RDP is the standard, proven algorithm for this exact
problem (curve simplification from a dense captured stream) — one
tolerance value, naturally denser where the path actually curves,
sparser where it's straight, processes the whole capture rather than
deciding greedily point-by-point. Orientation: run RDP on position to
decide which samples survive, carry each surviving sample's already-
captured orientation along with it. Known gap, not designed around
preemptively: a pure hover-and-pan (position barely moving, orientation
changing a lot) would lose those orientation changes under position-only
RDP — worth revisiting only if that use case actually comes up.

**5. Path recorder's UI home: the existing old-preview code, not a new
tool.** *"Let's take advantage of our existing code. The crash was
mitigated. We need the preview in X_ITE."* Confirmed — matches §5's
finding that the crash-causing bugs (the `getField().setValue()` SAI bug
and the refresh-button teardown leak) were found and fixed earlier this
session, so "it used to crash" is no longer a reason not to build on it.

**Record Arc / Export placement — no longer fully open.** Having read
`runSceneArc`/`_sceneArcAdvance`/`_saveSceneArc` end to end: Record Arc
needs paths (with waypoints), agents/cultivars, an LLM adapter
configuration, and scene/take naming — all things that exist once Place,
Character Creator, Agents, and Paths are authored. It doesn't need
Events or Timeline/Dialogue to exist at all today (it calls `/voice/speak`
directly, bypassing both). Under the Actor/Timeline model this may
change — if dialogue moves fully into Timeline per §2, Record Arc would
need to read *from* Timeline-authored dialogue rather than each
waypoint's own `qaLines`, which would newly make it depend on Timeline.
That dependency shift, not module placement in the abstract, is the
actual open question — proposed for discussion, not resolved here.

---

## Part A — Nominal edit order to construct a complete MCCF scene

**Proposed, not yet author-confirmed** — a sensible default sequence,
made safe against out-of-order editing by §3's refresh-on-focus
mechanism rather than relying on the order itself being enforced.

1. **Scene setup** — name, dimensions. No dependencies.
2. **Place** — zones, cameras (already rebuilt this session),
   lights (future), generic placed Actors (fog/door/etc., once §1's
   composer-implementation question lands). Zones typically exist
   before waypoints reference them.
3. **Character Creator** — avatar authoring (skin, behavior clips,
   camera rig). Operates on avatar *files*, genuinely independent of any
   specific scene — could happen before a scene exists at all. Listed
   here because an author would usually want to know which avatars a
   scene needs before investing time per-avatar.
4. **Agents** — placing avatars into the scene, assigning Character
   Creator files.
5. **Paths / Path Recorder** — straight grid-click paths (existing) and
   the new fly-mode-captured curved paths (§5). Needs agents to exist;
   ideally Character Creator rig work done first if a parented camera
   should ride along a path.
6. **Events (repurposed old events editor)** — camera and light cues,
   per the author's stated plan. Needs paths/waypoints, agents, and
   placed cameras to reference.
7. **Timeline / Dialogue (new)** — Actor-scoped tracks, steps, dialogue
   lines, structured triggers. Needs Actors (all types) to exist. This
   is where dialogue authoring now lives, per §2.
8. **Lighting** — deferred per its own spec's priority; joins Place once
   its research phase lands.
9. **Record Scene Arc** — exercises the fully-assembled scene (paths,
   agents, dialogue/timeline all wired). Needs everything above to
   already exist, which is why it's last among authoring-adjacent
   actions — see the open question in §6 about whether this splits into
   two related-but-distinct recording modes (dialogue/arc capture vs.
   path capture).
10. **Export** — always last.

## Part B — Task list, in logical order

### Phase 0 — Done this session (context, not new work)
Camera model consolidation, Character Creator camera rig chain, multi-
path playback orchestration, WP1/WP4, various confirmed bug fixes. Full
detail in `MCCF_Camera_Model_Revision_v0.1.md`.

### Phase 1 — Settle the one remaining open fork
1. Decide §1's composer-implementation question: does `placedAgents`
   get restructured for the Actor model, or does reconciliation happen
   only at generator/export time?

### Phase 1 — No longer a decision, an implementation task
1. Build the export-boundary adapter reconciling `placedAgents`/
   `placedCameras`/`zones`/(future prop structures) into the uniform
   Actor view the generator needs, per §6 item 1's decision. Follow the
   `REAL_MANIFEST_TYPES`/`MANIFEST_BY_TYPE` pattern already proven in
   the Timeline prototype rather than designing a new shape.

### Phase 2 — Record Arc / Path Recorder
2. Build the path recorder inside the existing (crash-fixed) old-preview
   code, per §6 item 5 — `addFieldCallback` on the bound Viewpoint's own
   `position`/`orientation` fields (§6 item 2), not `ProximitySensor`.
3. Implement RDP (Ramer-Douglas-Peucker) decimation on the captured
   position stream, carrying each surviving sample's orientation along,
   per §6 item 4.
4. Design the new independent-path data structure and the `ROUTE`-setup
   mechanism for binding arbitrary objects to a named path (§5).
5. Swap `PositionInterpolator`/`OrientationInterpolator` for
   `SplinePositionInterpolator`/`SquadOrientationInterpolator` in the
   path-export code, for recorded/curved paths specifically.
6. **Small, independent, do anytime:** fix `applyArcCV`'s hardcoded
   `pos_y: '0.00'` to `pos[1].toFixed(2)` — real correctness bug, zero
   regression risk, unrelated to the smooth-vs-snap decision (§6 item 3
   keeps the preview itself rough on purpose).
7. *(Separate, lower priority, not blocking anything above)* Reconsider
   `agent_track` as `PositionDamper`/`OrientationDamper`-based live
   tracking instead of baked keyframes (§5).

### Phase 4 — The actual V5 generator build

**Architecture note, Day 78, worth recording before this phase starts:**
now that `dispatcher.js`/`timeline-xml.js`/`field-map.js`/
`dialogue-xml.js` have all been read in full, two genuinely different
paths exist for this phase, not one:

- **(a) Compile to native X3D** — the Scene Integration Spec's actual
  §1 decision. Generate `<Script>` nodes reproducing `dispatcher.js`'s
  logic in X3D ECMAScript SAI, baked into the exported scene — the
  scene stays self-contained, playable by any X3D browser, no external
  JS dependency at runtime. `dispatcher.js` confirmed genuinely
  rendering-agnostic (never touches X_ITE/`TimeSensor`/`ROUTE`) —
  the characterization that justified this decision holds up against
  the real file, not just the earlier summary of it.
- **(b) Load the real files as-is into `mccf_x3d_loader.html`**, and let
  them drive the already-exported scene via SAI — the same way
  `pbStepSession`/`applyArcCV` already drive scenes today. Far less new
  code (no generator to build at all, just an integration layer), at
  the cost of scenes no longer being self-contained outside MCCF's own
  loader.

**Not re-opening this — (a) is the standing decision, made deliberately,
for a real reason (self-contained scenes).** Recording (b) here because
it's a genuine fork that exists now that the real files are in hand,
not because it should be relitigated without cause.

8. Build the native-X3D generator: Track/Step/Cue XML → `TimeSensor`/
   `Interpolator`/`ROUTE`/generated `<Script>` nodes, per (a) above,
   using `dispatcher.js` as the verified spec, following the
   already-proven `SoundFader_*` pattern. Concrete detail now available
   from the real file, not just its summary: the Welder default
   (starting a step displaces whatever's active on that track,
   generalized to every track kind including camera cuts), the
   interrupt/wait/overlap collision policies, and the field-lock
   priority system (a `declared` write locks a field for its step's
   duration; `continuous` writes are refused, not queued, while that
   lock holds) all need real equivalents in generated Script logic, not
   just the five verbs and six trigger types in isolation. One concrete
   limitation to carry into the generator, not paper over: `blend`
   arbitration only has a real multiplier function for two fields today
   (`walkPace`, `swingSpeed`, both in `worked-manifests.js`'s `AVATAR`
   manifest) — any other field marked `blend` currently falls through
   to plain replace-on-write. A second real gap, from the original
   design doc itself, never resolved since: no camera release/stop verb
   exists — a cut always displaces whatever was bound before it, with no
   way to return to the previous camera. Real design work, not just
   implementation, if this generator is meant to support it — flagged in
   `MCCF_Actor_Architecture_Design_v0.2.md` §7/§12 as explicitly open.
9. Wire the Timeline/Dialogue editor's authoring UI to the same
   refresh-on-focus scene-data pattern built this session (§3).
10. **No longer needs a migration plan designed — one already exists.**
    Wire `parseLegacyWaypointLines()` (confirmed real, working code in
    `dialogue-xml.js`) into the actual migration path for existing
    scenes; Waypoint drops dialogue content going forward, Timeline's
    Dialogue tab becomes sole authority, per §2.

### Phase 5 — Consolidate Events Editor scope
11. Confirm the events editor keeps camera + light cues only, per the
    author's stated plan — strip anything now owned by Timeline/
    Dialogue.
12. Update Record Arc to read dialogue from Timeline-authored data
    instead of each waypoint's own `qaLines`, once (10) lands — this is
    the real dependency §6 found, not a module-placement question.
    Record Arc doesn't touch Events or Timeline today (it calls
    `/voice/speak` directly), so this dependency is new, introduced by
    (10), not pre-existing.

### Phase 6 — Lighting
13. Deferred, per its own spec's already-settled priority (last in the
    Scene Integration Spec's own module order too).

### Housekeeping, can happen anytime, no dependencies
- `MCCF_Camera_System_Spec_v1_3.md` revision pass.
- Wire `dispatcher.js`'s `fireArcComplete()` to Chorus's `fire_chorus()`
  — still deprioritized, still real.
- Confirm the events editor teardown fix live, and test the two
  pending-live items from Phase 0 (media paths, `SHOT_ATTACHED` fold).

---

## Part C — File checklist per phase

**One critical rule for all of this, worth stating plainly: for anything
in the "touched this session" list, load the *delivered/output* version,
never the original upload.** Several of these files carry real bug
fixes from today (the `getField().setValue()` fixes, the multi-path
DEF-collision fix, WP1, `garden_001`, media paths, the `SHOT_ATTACHED`
fold, and more) — the original uploads don't have any of that. Starting
a fresh phase from an original would silently reintroduce already-fixed
bugs. If continuing in a fresh session, re-upload from the output
folder's current copies, not from wherever the files originally came
from.

**Phase 1, task 1 (export-boundary adapter):**
- `mccf_scene_composer.html` — to edit (delivered version).
- `worked-manifests.js` — **in hand, read in full, Day 78.** Confirms
  exactly three manifests (`AVATAR`/`SCENE_FOG`/`DOOR`), field-by-field,
  sourced from `MCCF_Actor_Architecture_Design_v0.2.md` §4.2 — a doc
  this session hasn't seen yet (see below).
- `field-map.js` — **in hand, read in full, Day 78.** Confirms the
  inline `<MetadataSet name='fieldMap'>` X3D serialization directly
  (matches the Day 72 decision found earlier via conversation search),
  plus real validation rules (`affect-writable` fields require
  `channel`/`curve`/`arbitration` together; any other reach type must
  *not* have them).

**Phase 2 (Record Arc / Path Recorder):**
- `mccf_events_editor_prototype_2.html` — to edit (delivered version,
  already has the SAI and teardown fixes this work builds on top of).
- `mccf_scene_composer.html` — to edit (delivered version).
- `mccf_x3d_loader.html` — to edit (delivered version — the `pos_y` fix
  and any Spline-interpolator playback wiring land here).
- `mccf_api.py` — to edit if new server endpoints are needed for saving/
  loading named paths (delivered version).

**Phase 4 (the generator build):**
- `dispatcher.js`, `field-map.js`, `timeline-xml.js`, `dialogue-xml.js`,
  `worked-manifests.js` — **all five in hand, read in full, Day 78.**
  This phase is much closer to startable than earlier drafts of this
  doc suggested — never blocked on these being written, and now not
  blocked on having their content either.
- `bridge-test.js` — **still genuinely not located.** The Node-side test
  harness these five files were verified against (per Day 74 comments
  inside them, now confirmed directly, not inferred) — not seen in the
  `static/js/` listing, may live elsewhere in the repo. Worth checking,
  not required to start Phase 4, useful for verifying the generator's
  output the same way the original files were verified.
- `MCCF_Actor_Architecture_Design_v0.2.md` — **in hand, read in full,
  reconciled against §1 above, Day 78.** The Day 71 foundational design
  — §1 has been corrected and sharpened against it directly, not left
  as a conversation-search reconstruction.
- `mccf_scene_composer.html` — to edit (delivered version).
- `mccf_timeline_dialogue_prototype_v2.html` — have it, read-only
  reference (the source format the generator consumes).

**Phase 5 (consolidate Events Editor scope):**
- `mccf_events_editor_prototype_2.html` — to edit (delivered version).
- `mccf_playback.py` — to edit, for the Record Arc → Timeline dialogue
  dependency (delivered version — unchanged this session, but still the
  real current file, not the original).

**Phase 6 (Lighting):** deferred, no file needs yet.

**Housekeeping items:** `MCCF_Camera_System_Spec_v1_3.md` (have it,
unmodified, to edit for the revision pass); `mccf_chorus.py`,
`mccf_playback.py`, `mccf_api.py` (all have delivered versions, for the
dispatcher/Chorus wiring).
