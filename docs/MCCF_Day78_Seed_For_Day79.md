# MCCF Day 78 — Seed for Day 79

*Written proactively, mid-session, on the author's own call ("we may hit a
session limit soon... better safe than sorry") rather than at a natural
end. Two bodies of work this session: (1) Phase 1 task 1 of
`MCCF_V5_Integration_Nominal_Order_and_Tasklist_v0.1.md` — the
export-boundary Actor adapter — built, tested, and UI-verified live,
start to finish, no surprises. (2) Phase 2 of the same tasklist — the
path recorder — which took two real, wrong turns before landing on a
working mechanism, and which is the reason this doc exists: the
Tasklist's own §6 mechanism claim for path recording is now confirmed
wrong and needs treating as superseded, not just "worth re-checking."
Same discipline as Day 77's seed doc: mark confirmed-live vs.
not-yet-tested honestly, and say plainly where an existing doc turned out
to be wrong rather than glossing over it.*

---

## Part 1 — Phase 1, task 1: Actor export-boundary adapter — done, confirmed live

**`actor-adapter.js`** (new file, `static/js/`) — reconciles Composer's
`placedAgents`/`placedCameras`/`zones` into the uniform Actor view
(`{id, actorType, fieldMap, trackDefs, instance}`) the Phase 4 generator
will eventually consume. Matches the Tasklist's own settled answer to
its §1 fork: **zero changes to `placedAgents`/`placedCameras`
themselves** — this is a read-only boundary translation, not a
Composer-side data-model change.

- Zones are explicitly **not** converted into Actors (Design Doc §2:
  "the thing that fires the verb" vs. "the thing that receives it") —
  passed through unconverted, for trigger-authoring purposes only.
- Avatar uses the real, author-confirmed `AVATAR` manifest from
  `worked-manifests.js`. Camera has no worked manifest anywhere in the
  source docs, so it got an honest empty field map (`fields: []` —
  "track-only, not affect-reachable," legal per Design Doc §4.1) rather
  than an invented one — flagged in the file's own comments as a
  judgment call to revisit if a real affect-writable camera field is
  ever wanted.
- **Real bug this reconciliation surfaced, not previously checked
  anywhere**: Composer's own `registerId()` only guards id uniqueness
  *within* one type — `zones`/`placedCameras`/`placedAgents` are three
  independent namespaces today, so an Avatar and a Camera can share a
  name with no warning from Composer's own UI. But `dispatcher.js`'s
  `actors` object and Timeline XML's `<Actor name="...">` both resolve
  against one flat, scene-wide id space. The adapter now detects this
  cross-namespace collision and refuses to build a registry rather than
  silently aliasing two different Actors onto one id.
- Tested standalone (`actor-adapter.test.js`, 5 cases, all passing,
  including a live `Dispatcher` registration + `start()` call) *and*
  wired into Composer's UI: a "Validate Actors" button in the Export
  panel, with a **persistent, structured** result panel — not a toast
  that vanishes, not a "see console" dead end. A collision shows both
  colliding objects as peers (type, name, and a direct action —
  "Edit Camera →" jumps into that object's real edit form; "Select
  Avatar" highlights it, since Avatar names aren't renamable from this
  UI at all), not one object implied-correct and the other
  implied-wrong.
- Two real bugs found and fixed *while* building this UI, worth naming
  since they're the kind of thing that could resurface elsewhere:
  1. `toast(msg, true)` (the error-toast path) was scheduling its own
     auto-dismiss at `0`ms instead of never auto-dismissing — every
     error toast in the whole app was flashing and vanishing before it
     could be read. Fixed to rely on the toast div's own
     `onclick="this.className=''"` for error dismissal instead.
  2. `.expopt`'s CSS is `display:flex` for exactly two children (label +
     button) — appending a third child (a results panel) squeezed it to
     invisible width instead of rendering below. Fixed by nesting the
     original two-child row inside a non-flex wrapper, with the result
     panel as a proper sibling below it, not a flex child beside it.

**Nothing pending here.** This part of the session is closed.

---

## Part 2 — Phase 2: Path Recorder — real story, two wrong turns, now working

### 2.1 What's actually done and confirmed live

- **`path-recorder.js`** (new file, `static/js/`) — RDP (Ramer-Douglas-
  Peucker) decimation + the new independent `RecordedPath` data
  structure (Tasklist §5's "needs confirmation" item, now built).
  Deliberately **not** a variant of today's `<Path agent="...">` — that
  element bakes in single-agent ownership; a captured path is meant to
  be reusable across objects, so it gets its own `<RecordedPath>`
  element, its own file, its own namespace (`recordedPaths{}` in
  Composer, parallel to but separate from `paths{}`).
- **Task 6** (the one-line `pos_y` fix) — done, and turned out to be
  three spots, not one: `mccf_x3d_loader.html`'s `applyArcCV` was
  hardcoding Y=0 in the SAI write, but `mccf_scene_composer.html`'s
  `_sceneArcAdvance` was *also* hardcoding the broadcast payload's
  `pos_y` before it ever reached the loader — fixed both, plus the arc
  row's own logged `pos_y`. Currently a no-op in practice (no waypoint
  height-authoring UI exists anywhere yet, so `wp.position[1]` is always
  0 today) but no longer silently clamping a field that will matter the
  moment elevation authoring exists.
- **Path recorder UI**, live in `mccf_events_editor_prototype_2.html`:
  Record/Stop toggle, live sample counter, a Stop panel with tolerance
  retuning (rebuilds decimation live, before committing), Save/Discard.
  Composer's Scene Stats panel got a matching "Recorded Paths" row
  (click to expand: id, key count, tolerance, created-at, Delete) — the
  Events Editor got a lighter read-only "Saved Paths (N)" view of the
  same list, since the author asked to see it without tabbing back to
  Scene.
- **`buildInterpolatorX3D(path, opts)`** (in `path-recorder.js`) —
  compiles a validated `RecordedPath` into real, playable X3D:
  `TimeSensor` + `SplinePositionInterpolator` +
  `SquadOrientationInterpolator` + the four `ROUTE`s that wire them into
  a target Transform's `translation`/`rotation`. Tested standalone
  (structural checks: key/keyValue count parity, keys normalized to
  [0,1], required-`targetDEF` enforcement). **Deliberately not wired
  into `exportX3D()`/`buildX3DString()` yet** — it takes a `targetDEF`
  as a required parameter rather than inventing one, because *which*
  object a recorded path drives, and what triggers it, is Timeline/
  Dialogue authoring's decision (still not built), not something to
  hack around ahead of it. Confirmed with the author directly (Day 78):
  a recorded path is assigned to an Actor and a trigger inside the
  eventual Timeline editor, matching "any object with an exposed XYZ
  field... is a triggered event" — this is not a new architectural
  question, it's the same uniform-Actor-model answer Phase 1 already
  built toward.

### 2.2 The real story: two wrong mechanisms before the right one

This is worth recording in detail because it's exactly the kind of
X_ITE surprise this project has been bitten by before, and because the
Tasklist doc's own §6 item 2 turned out to state the wrong mechanism
with unwarranted confidence.

**Attempt 1 — poll `getActiveViewpoint().getField('position'/'orientation')`.**
Built on real, working precedent in this exact codebase
(`updateCamTelemetry` in `mccf_x3d_loader.html`) — but that precedent
was reading back a value *the codebase itself had just written* via
script, never reading live mouse/keyboard navigation. Those are
different claims. Result when tested: recording a deliberately-flown
curve produced 2 keys (RDP correctly collapsing a stream that was, in
fact, nearly motionless).

**Diagnosis, done properly, not by assumption:** added a raw-sample
bounding-box-spread + total-travel-distance diagnostic
(`_pathRecRebuild`'s console output) to isolate capture-side vs.
decimation-side failure *before* touching any code. Then the author ran
a direct, manual, two-call test in devtools:
```js
document.getElementById('vp-x3d').browser.getActiveViewpoint().getField('position').toString()
```
Same exact string both times, despite visibly navigating the viewport
in between. Rebinding to a *different named* Viewpoint DID change the
value. **Conclusively proves**: a bound Viewpoint's `position`/
`orientation` fields hold that node's *authored* value, not a live
navigation transform. Confirmed independently against X_ITE's own docs
(not just this one test): "Controlling the Viewpoint" states navigation
is tracked as a separate *offset*, never written into the Viewpoint
node's own fields.

**Attempt 2 (the actual fix) — `ProximitySensor.position_changed`/
`orientation_changed`.** Confirmed as X_ITE's own *documented* mechanism
for exactly this ("Sensing the Viewer" tutorial, stated outright, not
inferred) — this is not a workaround or "old-school fallback," it's the
first-class, correct API. The author's own instinct ("Plan B... use a
master proximity sensor") was right the whole time; what changed was
recognizing it as *the* answer rather than a fallback. Implementation:

- A scene-covering `ProximitySensor` (`MCCF_PathRecorderProx`), emitted
  unconditionally at scene-export time (no checkbox — the author's own
  call: "always there," one less thing to forget). Sized proportionally
  to the grid — **1.5× width/depth/height** (author's explicit design
  call, replacing this session's first-cut flat-margin sizing, which
  didn't scale across different grid sizes).
- Recorder now reads this sensor's `position_changed`/
  `orientation_changed` via the same polling mechanism as before (that
  part was never the problem — only *what* was being read was wrong).
  Checks `isActive` each tick, warns once (not spammy) if the camera
  exits the sensed region.
- `startPathRecording()` fails loudly with a clear `alert()` — author's
  explicit preference over a toast here: *"Alert is fine. I like those.
  They can't be skipped. Good UI choice for mandatory warnings."* — if
  the sensor isn't found in the loaded scene (stale/pre-Day-78 export).

**Result after the fix, confirmed live:** a deliberately-flown curve
produced 39 keys (up from 187 raw samples) — real curvature preserved,
not collapsed to a straight line. This is the first attempt where the
underlying mechanism was actually correct, not just differently broken.

### 2.3 A second real bug, found only because the sensor fix didn't
### show up on the first two "fresh" re-exports

Two exports in a row came back missing `MCCF_PathRecorderProx` despite
genuinely fresh timestamps — not a caching problem. Root cause: **this
codebase has two separate, parallel functions that each independently
build the X3D scene string** — `exportX3D()` (wired only to the
"Export X3D" button) and `buildX3DString()` (what `sendToLauncher()`
actually uses — which is what *both* "Send to Launcher" *and* the
Events Editor's Refresh button call). Every fix made to `exportX3D()`
this session (the sensor, originally task 6's `pos_y` fix too) was
going into the one function that was never actually in the live
preview/recording path. Confirmed unambiguously: `buildX3DString()`'s
output has never included `exportX3D()`'s own long-standing "Generated:"
comment or generator meta tag, in any version of this file — not a
regression, a pre-existing structural duplication.

**Fixed**: the same `MCCF_PathRecorderProx` sensor (identical 1.5×
sizing) added to `buildX3DString()` too, verified against a real
exported file (`grep`-confirmed present, correct `center`/`size`
values) before declaring it done.

**Standing risk, not resolved, flagged plainly**: this duplication means
any *future* edit to `exportX3D()` needs deliberately mirroring into
`buildX3DString()` (or vice versa) or it silently won't reach the real
preview/recording path — exactly the failure mode that cost two full
round-trips of "fresh export, still broken" this session. Worth a real
refactor (one function, one call site each) at some point — not done
here, correctly out of scope for a bug-fix pass, but the risk shouldn't
be forgotten a second time.

### 2.4 Two more small bugs, found and fixed along the way

- After a recorded path is saved, the Events Editor's own "Saved Paths"
  badge stayed stale (showed 0) until some unrelated trigger caused
  Composer to resend scene data — fixed by resending immediately after
  storing a save, not waiting on a later trigger.
- Composer's own recorded-path storage code called `updateSummary()`
  when it needed `updateStats()` — two separate functions in this file
  that don't call each other; the stat counters live in the latter.
  Real, easy-to-repeat mistake given the similar names — worth knowing
  they're not interchangeable if touching either again.

---

## Part 2.5 — Housekeeping pass, done after this doc was first written

This doc was written mid-session, proactively, before hitting a suspected
session limit. The limit didn't hit — the author asked for the "easy
bits" from Part 4's original list before stopping for the day. Recording
what actually got done, same discipline as everything above: confirmed
vs. built vs. still-real-gap, not just "done."

### Phase 0 confirmations — closed

- **Media directory paths** (music/soundeffects/convolver) — confirmed
  good, tested live. No further action.
- **`SHOT_ATTACHED` fold** (`agent_orbit`/`agent_track`) — confirmed
  good, tested live. No further action.
- **Arc-order finding** ("Play All works as long as I select the
  level-one arc") — **not a bug**. Matches the loader's own
  `pbActivateX3DTimers()` design: it hardcodes its lookup to
  `'Timer_'+safeName+'_1'`/`'Arrival_'+safeName` bare (no order suffix)
  specifically to arm an agent's *first* path, so starting from anywhere
  but the order=1 arc bypassing that entry point is expected behavior,
  not a defect. Author's own call: this is a **Users Guide note**, not
  a code task — deliberately deferred until "V5 is solid" and a larger
  Users Guide update happens. Do not "fix" this without the author
  re-opening it; it's working as designed.

### Chorus voice_actor → Cultivar wiring — done, real implementation, not a seam

`mccf_chorus.py` now actually does what
`MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md` §2/§3 specified — through
Day 77, `voice_actor` affected the captured Line's metadata but **never
changed which prompt built the LLM's actual response** (a real,
previously-unnoticed gap in the spec's own prior implementation, not
just an unfinished feature). Fixed:

- New `character_voice_prompt(actor_id, scene_context)` — the shared
  mechanism the spec calls for, built so a future regular-dialogue
  `mode="improv"` call site (still doesn't exist anywhere in this
  codebase — confirmed, not assumed) has something real to call when it
  lands.
- `_build_system_prompt` now branches: `voice_actor` set →
  Cultivar-driven prompt; not set → the old persona/tone path,
  unchanged (regression-tested).
- **Real Cultivar file format, confirmed directly by the author**
  (screenshots of `cultivars/*.xml` and the Character Creator UI) — not
  guessed. This corrected a wrong assumption already baked into the
  spec and this module's first draft: **there is no "Disposition"
  field anywhere in the real schema.** Real fields: `Description`,
  `Weights` (E/B/P/S), `Regulation`, `FailureMode` (optional — Cindy's
  own file has none), `SignaturePhrases`. Root element
  `<CultivarDefinition name="..." version="1.0" color="..."
  xmlns="http://mccf.artistinprocess.com/cultivar/v3">`.
- **Filenames are not systematic** — confirmed from the author's own
  directory listing (`cultivar_Jack.xml`/`cultivar_Salida.xml`, proper
  names, vs. `cultivar_the_advocate.xml`/`cultivar_The_Steward.xml`,
  role names, inconsistent casing). `_default_cultivar_loader` handles
  this with a fast direct-filename path first, falling back to a
  directory scan matching by the file's own `name=` attribute,
  case-insensitively — tested explicitly against a case that would
  silently break a naive implementation (`"The Steward"` as
  `voice_actor` doesn't literally match `cultivar_The_Steward.xml` via
  direct path join, because of the space).
- **One assumption not yet verified**: `CULTIVARS_DIR = "cultivars"` is
  relative — correct only if `mccf_api.py`'s working directory is
  `mccf_full/` when it starts. If Chorus firing can't find any
  Cultivars in production, check this first.
- 8 tests passing (real-format lookups, unknown-actor handling,
  end-to-end prompt generation, 3 regression checks against the
  pre-existing no-voice_actor/graceful-degradation paths).
- **`fireArcComplete()` ↔ `fire_chorus()` wiring** — explicitly NOT
  done. Explained to the author what it means (two independently-built
  "arc completed" detectors — `dispatcher.js`'s, unused since Timeline
  isn't live yet, and `mccf_chorus.py`'s, which is what's actually
  firing today) — still correctly deprioritized, costs nothing until
  Timeline is running.

### `MCCF_Camera_System_Spec_v1_3.md` — revision pass, done honestly, not fully

This doc's own §2 ("What this retires") already said *"The three-class
framing in `MCCF_Camera_System_Spec_v1_3.md`. Needs a revision pass —
not yet written."* — real, pre-acknowledged debt. What actually
happened, deliberately bounded:

- **A status banner added at the top**, not a full rewrite. States
  plainly that §1–§3/§7 (the static/relational shot-type taxonomy) are
  superseded by `MCCF_Camera_Model_Revision_v0.1.md`'s placed-vs-parented
  model, and that §4/§5/§6/§10 are still accurate. **The actual v1.4
  rewrite reflecting the new model was deliberately NOT done** — that's
  real design-transcription work (DEF naming/seeding rules, roll
  composition, the new Place Editor shell) that deserves the author's
  own review, not a rushed condensation. Whoever picks this up next
  should treat `MCCF_Camera_Model_Revision_v0.1.md` §1–§4 as
  authoritative over this doc's §1–§3/§7 until that rewrite happens —
  don't re-derive that decision, it's already made.
- Two small corrections applied inline, both already flagged elsewhere
  as needed: §3a's "generic across every avatar" language (superseded
  Day 76, per Avatar Camera Rig Manifest Spec) and §9's `track` status
  (the proto already existed as of Day 64 — was never a future
  candidate).
- **New §4 addition**: the full ProximitySensor-vs-Viewpoint-fields
  finding from Part 2.2 above, written in the same rigorous format as
  §4's existing entries (code example, what broke, why it matters,
  sourced against X_ITE's own docs with links). This is the same
  finding, just given a permanent home in the doc that owns X_ITE SAI
  corrections, not just this seed doc.

---

## Part 3 — Corrections to `MCCF_V5_Integration_Nominal_Order_and_Tasklist_v0.1.md`

Treat these as superseded, not just "worth re-checking" — both are now
disproven or completed, not merely uncertain:

- **§6 item 2** ("`addFieldCallback` on the bound Viewpoint's own
  position/orientation fields") — **wrong**, confirmed both by direct
  empirical test and by X_ITE's own documentation. The real mechanism
  is `ProximitySensor.position_changed`/`orientation_changed` on a
  scene-covering sensor. See Part 2.2 above for the full evidence chain.
  Any future doc referencing this Tasklist's camera-track-recording
  mechanism should point at the ProximitySensor approach instead.
- **§6 item 5** ("recorder lives inside the existing preview code") —
  this one held up and is now *built*, not just decided. No correction
  needed, just noting it moved from "settled" to "shipped."
- **Phase 2 task list** (tasks 2–4, 6) — all complete as of Day 78; task
  5 (Spline interpolator generation) is **partially** complete — the
  compile function (`buildInterpolatorX3D`) is built and tested, but
  not wired into either export function, deliberately pending Timeline/
  Dialogue authoring's binding UI (see §4 below).

---

## Part 4 — What's still open, going into Day 79

**Not a design question — confirmed directly with the author, Day 78:**
a recorded path is assigned to an Actor (any type with an exposed
position field — not camera-specific) and a trigger, inside the
Timeline/Dialogue editor once that's built (Phase 4). This matches the
uniform Actor model Phase 1 already built toward — no new architectural
fork here, just the next piece of already-settled architecture.

**Concrete next tasks, in likely order:**

1. **Phase 4 proper** — the actual Timeline/Dialogue integration into
   `mccf_scene_composer.html`. This is the real unblock: once an author
   can pick "this recorded path, this Actor, this trigger" in a UI,
   `buildInterpolatorX3D` is ready to be called with a real
   `targetDEF` — no changes needed to the function itself for that to
   happen.
2. **When `buildInterpolatorX3D`'s output does get spliced into a real
   scene export**, it needs to land in *both* `exportX3D()` and
   `buildX3DString()` — see §2.3's standing-risk note. Whoever does this
   should grep for the other function immediately, not discover the
   duplication the hard way a third time.
3. **The `exportX3D()`/`buildX3DString()` duplication itself** is worth
   a real refactor at some point — not urgent, but every session that
   touches scene-XML generation without knowing about this pays a tax
   until it's unified.
4. Two small, real, previously-flagged items still sitting unaddressed,
   lower priority: `fireArcComplete()` ↔ `fire_chorus()` still unwired
   (author's own "old system works fine, no problem yet" — unaffected
   status, now also explained plainly to the author in Part 2.5); lighting
   stays explicitly last/pre-design.
5. **`MCCF_Camera_System_Spec_v1_3.md`'s actual v1.4 rewrite** — the
   status banner added Day 78 (Part 2.5) explicitly defers this; it's
   real design-transcription work (DEF naming/seeding, roll composition,
   Place Editor shell) that needs the author's own review, not something
   to condense solo. Not urgent — the banner keeps the doc honest in the
   meantime — but don't mistake "banner added" for "rewrite done."
6. **`mccf_chorus.py`'s `CULTIVARS_DIR` assumption** — untested against
   the real running server (relative path, assumes `mccf_full/` as
   working directory). Cheap to verify, not yet verified.
7. **Users Guide, massive update, explicitly deferred by the author**
   until V5 is solid — the arc-order note (Part 2.5) is the first
   confirmed item queued for it, not the only one likely to accumulate
   before that pass happens.

---

## Part 5 — Files delivered this session (Day 78)

**New:**
`actor-adapter.js`, `actor-adapter.test.js`, `path-recorder.js`,
`path-recorder.test.js`, this seed doc.

**Modified, delivered versions differ from what was uploaded at session
start — use these, not the originals:**
`mccf_scene_composer.html`, `mccf_events_editor_prototype_2.html`,
`mccf_x3d_loader.html`, `mccf_chorus.py`,
`MCCF_Camera_System_Spec_v1_3.md`.

**If picking this up in a fresh session, bring:**
- This seed doc (the real narrative — what was tried, what was wrong,
  what's actually confirmed live).
- The seven modified/new JS/HTML/Python files above (delivered
  versions).
- `MCCF_Camera_System_Spec_v1_3.md` — use the delivered version (status
  banner + corrections + new §4 finding), not the original upload.
- `MCCF_Camera_Model_Revision_v0.1.md` — unchanged, but now the
  *authoritative* source for camera shot-taxonomy questions, per the
  banner added to the Spec above. The actual v1.4 rewrite folding this
  into the Spec proper is still not done — real remaining work, not
  forgotten.
- `MCCF_V5_Integration_Nominal_Order_and_Tasklist_v0.1.md` — still the
  right doc for Phase 4/5/6 task detail, **with Part 3 above applied
  as a correction layer on top of it**, not read standalone.
- `MCCF_Actor_Architecture_Design_v0.2.md` — unchanged, still accurate,
  still the reference for field-map/track/Actor shape.
- `MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md` — still accurate for
  the architectural decision; note Part 2.5 above corrects its assumed
  Cultivar field list (no "Disposition" field — see `mccf_chorus.py`'s
  own comments for the confirmed real shape).
- If Cultivar loading needs debugging: `cultivars/*.xml` are the real
  files (author's own machine, `mccf_full/cultivars/`) — not uploaded
  to this conversation, but their format is now fully documented in
  `mccf_chorus.py`'s comments and confirmed by direct example.

---

*Same closing discipline as Day 77's seed doc, and it earned its keep
again this session: two mechanisms were tried and one was wrong, and
the only reason that's known for certain — not suspected, known — is
that a diagnostic got built before trusting a "fix," and a direct
manual test got run before accepting a doc's own stated mechanism. The
Tasklist's §6 item 2 was written with the same confident, cited tone as
everything else in that doc, and it was still wrong. Confirm against
the real build, not against how authoritative a prior doc sounds — that
's the pattern this session re-earned, not just repeated.*
