# MCCF Camera Model Revision — v0.1

*Day 77. Companion to `MCCF_Camera_System_Spec_v1_3.md`,
`MCCF_Avatar_Camera_Rig_Manifest_Spec_v0.1.md`, and
`MCCF_Scene_Placement_Module_Consolidation_v0.1.md`. Grew out of Day 77's
opening item — confirming the live camera-preview bug fix in the browser —
and turned into a real architecture correction once the confirmed bug
(item 1) led into a design question (item 3's neighbor, unplanned) that
turned out to be bigger than a bug. No further code beyond the item-1
preview fix was written this session; everything below is decided but
not yet implemented.*

## Status banner

- ✅ **Item 1, first half — Place→Cameras panel confirmed correctly
  wired end-to-end.** Live in-browser test (Cam_Wide1: placed, edited,
  exported, selectable in X_ITE, persisted across reload) confirmed the
  panel works. The "broken" memory belonged entirely to the old events
  editor, not this panel. No code change needed here.
- ✅ **Item 1, second half — live camera preview SAI write-path bug,
  fixed and confirmed.** `mccf_events_editor_prototype_2.html`'s
  `_previewCameraShot()` used `getField('translation').setValue(...)` /
  `getField('rotation').setValue(...)` — the pattern Camera Spec v1.3 §4
  already proved unreliable. Replaced with direct property assignment
  (`camXform.translation = …`, `camXform.rotation = …`), matching the
  Loader's already-proven pattern. Single call site, lines ~1523–1524.
  **Confirmed in-browser same day:** edited cue values exported,
  persisted, and displayed correctly on reload/re-select — the write is
  landing reliably. What surfaced *beyond* that (initial framing not
  matching the shot-type label) was a separate, deeper finding — see the
  camera-model revision below — not a failure of this fix.
- ✅ **`subject2` gap on relational shots (Over Shoulder, Two Shot) —
  confirmed real, ruled not a problem.** `_previewCameraShot()` never
  reads `cue.subject2` even though the inspector collects and saves it.
  Under the camera model below this is moot: relational framing is now
  the author's job at placement time, not a live two-subject formula, so
  the gap doesn't need fixing — it needs to stop mattering, which the
  model change below already achieves as a side effect.
- ✅ **Camera model — substantially revised. Camera Spec v1.3's
  three-class model (Class 1 parented / Class 2 baked-static / Class 3
  free-world-space-compute-once) is confirmed stale.** It still frames
  the shot-type formula (`SHOT_PRESETS`/`_prevComputeCamPos`/
  `_prevLookAtOrientation`) as legitimate scene-graph machinery. It
  isn't, under the new model — see below. `MCCF_Camera_System_Spec_v1_3.md`
  needs a revision pass to replace the three-class framing with the
  placed/parented split below; not done this session.
- ⬜ **Place tab lineage note (historical, not architectural):** the
  Place tab is itself an evolution of the older events editor, not a
  separate lineage that happened to end up next to it. Relevant context
  for anyone reading the codebase's history, not a decision that changes
  anything above.
- ✅ **Place Editor shell — settled, generalized.** Not Cameras-specific
  — extends Day 76's Place-module consolidation with a live X_ITE center
  pane, shared across any proto family with something optical to look
  at (Cameras first, Lights later). Retires the current 2D-grid-only
  Free Camera panel. Built natively in the composer, not shared with the
  events editor file. Selecting a placed object binds X_ITE to its own
  view — look-through-the-lens. Efficiency of the pattern is an open
  bet until built and tested. See §3.
- ✅ **Zones/Waypoints/Paths stay on the current shell — settled.** They
  do not move onto the new Cameras shell; the live-preview pane's value
  doesn't apply to purely 2D-positional objects, and it keeps this
  session's scope from expanding further. See §4.
- ✅ **Roll — implemented and confirmed working in-browser, Day 77.**
  Composition order from §1 verified correct: `FreeCamera` proto gets a
  third nested `Transform` (`RollXform`, local Z, innermost) plus a
  `cam-roll` slider threaded through placement, editing, both export
  paths, and scene-reload restore in `mccf_scene_composer.html`. **One
  real bug found and fixed along the way, worth recording:** the export
  path that writes the `<ExternProtoDeclare name="FreeCamera">` header
  stub is a *separate* function from `buildFreeCamerasX3D()` and wasn't
  updated in the first pass — X3D requires this local stub to mirror the
  proto's actual field interface, so an undeclared `roll` field meant
  the browser silently dropped the value with no error at all: correct
  data in the file, zero visual effect. Found by testing the full
  round-trip (place → roll → export → inspect file → confirm proto
  instance correct → find the second declaration site) rather than
  trusting the first-pass code read. Fixed; user-confirmed live in
  X_ITE (~40° canted horizon, matching the set value).
- ⬜ **Open items remain** — see §5. Auto-numbered instance naming and
  shot-type preset seeding (both originally scoped alongside roll) are
  deliberately deferred, not done — they need the subject-relative
  seeding formula and a subject picker brought into the composer, real
  added complexity kept separate from roll's clean, self-contained fix.
- ✅ **Character Creator camera rig authoring — implemented across all
  four files, Day 77.** Item 4 done, plus the architecture conflict
  found while scoping it (below) resolved as part of the same pass.
  Not yet tested live.
  - **Conflict found and resolved:** Composer's `buildAX3D()` was still
    unconditionally emitting generic `VP_{name}_Eye`/`VP_{name}_Side`/
    `CAM_OrbitProto_{name}`/`CAM_TrackProto_{name}` for every avatar —
    exactly the "Composer-side generic fallback rig" the Avatar Camera
    Rig Manifest doc (Day 76 §4) had already decided to reject, never
    implemented. Fixed: that injection is now gated on a per-avatar
    manifest fetch (`_camRigManifestCache`/`camRigFetchManifest()`),
    only emitting `IMPORT` statements for rig types the avatar's
    manifest actually lists.
  - **A second, deeper conflict surfaced along the way:** the real rig
    now lives inside the avatar's own `Inline`d file, but
    `mccf_x3d_loader.html`'s `_bindNamedViewpoint()`/
    `_executeAgentOrbit()`/`_executeAgentTrack()` all used plain
    `getNamedNode`, which — per the codebase's own established comment
    on `pbActivateX3DTimers` — does not resolve nodes inside an `Inline`
    scope in X_ITE 11.6.x+; only `getImportedNode` does, via an
    `EXPORT`/`IMPORT ... AS=` pair (the same pattern already proven for
    behavior timers). All three Loader functions now try
    `getImportedNode` first, falling back to `getNamedNode`. Naming
    deliberately unchanged (`VP_{name}_Eye`, `CAM_OrbitProto_{name}`,
    `CAM_TrackProto_{name}`) so only the lookup *mechanism* changed, not
    any caller-side string construction.
  - **Server side (`mccf_hanim_api.py`):** `_look_at_orientation`/
    `_compute_orbit_camera_keyframes`/`_compute_track_camera_keyframes`
    are faithful ports of the Loader's math — including the Day 63
    `LOOK_AT_HEIGHT` correction (see next bullet) — functionally tested
    (37 keyframes, orbit sweep closes its 360° loop cleanly).
    `_write_camera_rig_nodes` writes `CAM_Eye`/`CAM_Side`/`CAM_Orbit`/
    `CAM_Track` into the avatar's own `<Scene>` with matching identity
    `EXPORT`s, idempotently replacing any previous rig rather than
    accumulating duplicates (unlike `_write_clip_nodes`, which is
    append-only — a deliberate difference, not an inconsistency: camera
    rig nodes are fixed-identity, one per avatar). `_ensure_camera_proto_declares`
    adds the `ExternProtoDeclare`s the avatar file needs to instantiate
    `AgentOrbitCamera`/`AgentTrackCamera` itself, with the relative path
    to `mccf_camera_protos.x3d` confirmed against `mccf_api.py`'s own
    comment on `X3DAssets`, not guessed. `_write_camera_rig_manifest`
    writes the sidecar XML — extended beyond the Day 76 doc's minimum
    ("listing the Viewpoints actually parented") to also carry full
    authored parameter values, not just boolean presence, specifically
    so Character Creator can reconstruct its form when reopening an
    avatar that already has a rig.
  - **Found and fixed while porting this math — a real staleness bug in
    this session's own earlier work:** the events editor's
    `_prevLookAtOrientation` (which this session's camera-seeding
    feature in `mccf_scene_composer.html` was based on) never received
    the Loader's Day 63 `LOOK_AT_HEIGHT` fix and has been aiming at the
    subject's ground point instead of eye height. `camSeedCompute()`
    corrected to match the Loader's actual math, not the stale copy —
    the events editor's own `_prevLookAtOrientation` is now moot for
    this purpose (subject-relative preview is being retired anyway,
    per §1/§2) but the discrepancy is worth knowing about if it's ever
    touched again before then.
  - **Character Creator (`mccf_character_creator.html`):** new "camera
    rig" tab — Eye/Side enable checkboxes, Orbit fields (radius/height/
    start angle/vertical angle offset/cycle duration/loop), Track
    fields (start/end offset/height/depth/vertical angle offset/
    duration). State (`_heCameraRig`) loads from the sidecar manifest
    on cultivar select (`heCameraRigLoadManifest`, resets to defaults
    first so a previous avatar's rig can't leak into a new one on a
    manifest 404) and is included in `heExport()`'s payload as
    `cameraRig`. Full JS syntax-checked clean via `node --check`.
- ✅ **Rig chain confirmed working live.** Orbit fired correctly when
  bound directly from X_ITE's own Viewpoints menu. Two real findings
  came out of that test, both fixed:
  - **Font sizes, unrelated to cameras but requested here — found via
    conversation search that this was raised before ("Jump field
    behavior in viewpoint binding," a presbyopia accommodation request)
    and only partially landed.** The events editor got fixed then (1
    straggler found and closed now); the composer (99 declarations) and
    Character Creator (101 declarations, including its 12px base) never
    did. All three bumped in a single-pass regex substitution (no
    chained double-substitution risk), plus `label` rules in the
    composer and Character Creator bolded (`font-weight: 600`) — the
    "larger *and* bolder" part of the original request, not just size.
  - **X_ITE's Viewpoints menu showed every avatar's orbit camera as the
    identical unqualified "Orbit," not "Cindy Orbit."** Root cause: the
    `description` field is baked once inside the avatar file at
    Character-Creator time, generic, since that file can't know what
    agent name it'll eventually be placed under — and `IMPORT` only
    renames the scene-graph binding (`AS=`), not the field value X_ITE
    actually displays. Fixed with a tiny per-instance `Script`
    (`CamDescInit_{name}_{type}`) that overrides `description` after
    import, using a `USE`-by-`AS=`-name field reference resolved at
    parse time — deliberately not a runtime `getNamedNode`/
    `getImportedNode` SAI call, so there's no ambiguity to get wrong.
    Matches this codebase's own established `Script` convention
    (`directOutput="true"`, plain-double-quoted `SFString` field
    values — confirmed against two other examples already in the file,
    not guessed).
- ⬜ **Sensed events in the old events editor don't fire reliably —
  noted, not yet diagnosed.** Raised during the same live test but not
  camera-specific and not enough detail yet to act on (which trigger
  type — proximity, waypoint-arrival, something else — and how the
  failure showed up). Recorded here so it isn't lost; needs the author
  to say more before it's actionable.
- ✅ **Multi-path DEF-collision bug — diagnosed, then fixed on request.**
  Composer's path export numbers each path's segments locally
  (`{agent}_{segmentIndexWithinThisPath}`), with nothing folding in the
  path's own identity into the DEF name. Any agent appearing in two or
  more separate paths in the same scene got duplicate DEF names
  (`Interp_Cindy_1`, `Timer_Cindy_1`, `Arrival_Cindy`, etc. — confirmed
  directly in the uploaded test scene, where Cindy has two paths and
  Jack only has one, explaining why Jack-only testing earlier this
  session never surfaced it). Duplicate DEFs make name-based resolution
  (`getNamedNode`, and ROUTE pairing by DEF) ambiguous — explains both
  "doesn't see the first WP" (wrong-path timer resolved) and "Cindy
  jumps instead of transitioning" (ROUTE pairing collapsed onto the
  wrong interpolator). Separately confirmed: the zone/agent
  `ProximitySensor`s in this codebase are ordinary X3D `ProximitySensor`
  nodes, which by spec can only ever sense the *bound viewpoint's*
  position, never an arbitrary avatar's — consistent with the author's
  explanation of why the newer waypoint-arrival/time-based event system
  exists.

  **Fix, in `buildInterpNodes`/`buildInterpRoutes`:** only paths with
  `waypointOrder !== 1` get a qualifying suffix (`_{order}`) folded
  into every DEF (`Interp_`/`Timer_`/`Dwell_`/`Arrival_`/`Kill_`).
  `order===1` paths keep today's exact unqualified naming — deliberate,
  not minimalism: `mccf_x3d_loader.html`'s `pbActivateX3DTimers()`
  constructs `'Timer_'+safeName+'_1'` and `'Arrival_'+safeName` bare,
  with no order suffix, to arm an agent's first path — qualifying
  `order===1` too would have silently broken that lookup. Also
  confirmed via the same investigation that `MCCFMaster`'s
  agent/segment-keyed functions (`startAgent`/`releaseDwellAgent`/
  `startNextTimer`) are dead code for movement — the Loader's own
  comment says so explicitly (*"MCCFMaster is NOT used for movement. No
  shared SFString bus."*) — so they were correctly left untouched
  rather than updated for a naming scheme they don't actually use.
  Verified two ways before delivering: simulated the exact fix against
  Cindy's real two-path scenario from the test file (zero collisions,
  and the `order===1` path's names come out byte-identical to today's
  scheme), and re-verified the whole file with the `html.parser`-based
  check from the bug below (not just `node --check`) since that's now
  the established method for this file.
- ✅ **Scene Composer broke immediately after the description-override
  fix above — found, root-caused, and fixed.** The new closing-tag
  line I added (`s+='  </Script>\n';`) contained the literal substring
  `</Script>` unescaped inside a JS string. Browsers' HTML parsers scan
  for `</script` case-insensitively *inside* a `<script>` element's raw
  text, regardless of JS string boundaries — hitting it terminates the
  whole `<script>` element early, dumping everything after it onto the
  page as literal text (exactly what the author's screenshot showed).
  Every *other* place in this file that closes a `<Script>` tag from
  within a string already knew this and splits it as `'</' + 'Script>'`
  — confirmed by checking all four existing occurrences before writing
  the fix, not assumed. My new line was the only one that didn't follow
  that established convention. Fixed to match.
  **Methodology gap this exposed, worth carrying forward:** the JS
  syntax checks used earlier this session (`node --check` on script
  content extracted via a hand-written regex) are blind to this entire
  bug class — a regex extraction doesn't reproduce a real HTML parser's
  raw-text/`</script`-terminates-early behavior, so it can pass clean
  even when the actual browser would truncate the file. Re-verified
  using Python's `html.parser` instead (which does implement that
  behavior correctly) — confirmed exactly one `<script>` element, and
  that it now reads the complete, un-truncated content. Worth using
  `html.parser`-based extraction rather than regex for any future check
  on a file that generates `<Script>`/other tag-like literal text from
  within its own inline script.
- ✅ **Seeding and auto-numbering — implemented and confirmed working,
  Day 77.** `CAM_SEED_TYPES`/`CAM_SEED_PRESETS` (static+relational groups
  only — `move` deliberately excluded, see §5 item 6) ported into
  `mccf_scene_composer.html`. Shot-type + subject dropdowns in the Free
  Camera form seed position/height/yaw/pitch/roll via
  `camSeedCompute()` (same offset-from-subject math as the events
  editor's `_prevComputeCamPos`/`_prevLookAtOrientation`, decomposed to
  match the three-Transform proto instead of a combined quaternion), and
  auto-number the name field (`Label_N`) without clobbering a manually
  typed name. Reuses the existing "Place on Map" button rather than
  adding new UI — seeding just sets `pendingPos` programmatically.
  User-confirmed live.
- ✅ **Events editor X_ITE teardown — real leak found and fixed, Day
  77.** The Day 76 doc's "tab-close needs explicit cleanup" framing was
  vague; tracing it precisely found a more concrete and more routinely-
  triggered bug: `refreshViewport()` (the "↺ refresh" button) mutated
  `#vp-x3d`'s `src` attribute directly, completely bypassing
  `loadX3DViewport()`'s cloneNode-replace teardown — every refresh click
  stacked a fresh WebGL context on the same element without releasing
  the previous one, reproducing the original crash pattern on a routine
  action, not an edge case. Fixed by adding a `force` parameter to
  `loadX3DViewport()` (skips only the same-src "nothing changed"
  shortcut; the actual teardown-and-recreate still runs) and routing
  `refreshViewport()` through it instead of raw attribute manipulation.
  Also confirmed while investigating: the outer Composer embeds the
  events editor as a single persistent iframe with a static `src`,
  shown/hidden via `display`, never reloaded on tab-switch — so there
  was no separate tab-switching leak beyond this one. Not yet tested
  live.
- ✅ **Multi-path playback orchestration — fixed, all in
  `mccf_x3d_loader.html`, not yet tested live.** Root cause (traced with
  `mccf_playback.py`, `mccf_chorus.py`, and `dispatcher.js`, all newly
  provided): the server creates one playback session **per path**
  (`PlaybackManager`'s session_id derives from `path_name`, not
  cultivar), but three client-side tracking structures —
  `_pbCultivarSessionMap`, `_pbArcComplete`, and the DEF-name
  construction inside `_pbAdvanceSeg`/`pbActivateX3DTimers` — were all
  keyed purely by agent/cultivar name, with no path/order dimension.
  An agent with two paths collided every one of them: only one of its
  two sessions could ever be tracked at a time, a stale `arcComplete`
  flag from path 1 satisfied `_pbWaitForGroup`'s wait for path 2
  immediately, and `Arrival_`/`Timer_` lookups always resolved to path
  1's bare-named nodes regardless of which group was actually running.
  This is separate from (and downstream of) the export-side DEF-
  collision fix from earlier today — that fix was necessary but not
  sufficient, since the *runtime orchestration* layer never knew the
  new, correctly-distinct names existed.

  **Design, deliberately narrower than full re-keying everywhere:**
  added one small map, `_pbAgentCurrentOrder[safeName] = order`, set
  once at the start of each order-group's processing and read by every
  function that constructs a path-specific DEF name. This works
  *because* group processing is already strictly sequential —
  `_pbWaitForGroup` blocks until group N fully completes before group
  N+1 starts — so exactly one order is ever "current" for a given agent
  at any moment. This avoided threading an explicit order parameter
  through the deep TTS/dialogue call chain (`pbReleaseDwell`'s three
  callers sit inside display/speech logic with no natural order
  context) while still fully fixing the bug.

  **Changed:** `_validateAndBuildOrderGroups` now also returns each
  path's `name` (normalized), needed to correlate a session back to
  "which of this agent's paths is this." `_pbPlayAllInner`'s per-group
  loop now resolves session IDs fresh per group (matching candidate
  sessions' cultivar list against the group's known path name, falling
  back to "the only candidate" when there's nothing to match against —
  the common single-path case), resets `_pbArcComplete`/
  `_x3dLastArrivedSeg` for that group's agents before starting, and
  calls `pbActivateX3DTimers` scoped to just that group instead of once
  upfront for the whole scene. `pbActivateX3DTimers` no longer resets
  `_x3dTimerActive`/`window._pbPollingSegment` itself (that would have
  wiped group 1's still-active state the moment group 2 called it
  again) — those resets moved to the one-time-per-Play-All block in
  `_pbPlayAllInner`; confirmed `pbPlay()`'s separate single-arc path
  already had its own independent resets and needed no change.
  `pbReleaseDwell`/`_pbAdvanceSeg` read `_pbAgentCurrentOrder` to build
  the correctly-suffixed DEF names. The no-`orderGroups` fallback path
  (scene XML unavailable, simultaneous firing) is unaffected — kept its
  original single upfront activation call, since it has no per-agent
  multi-path distinction to make.

  **Separately confirmed while tracing this, not yet acted on:**
  `register_chorus_api()` never actually sets
  `PlaybackManager.chorus_callback` anywhere — `fire_chorus()` is fully
  built and never automatically invoked on arc completion. This is the
  exact gap Day 76 flagged (`dispatcher.js`'s `fireArcComplete()` and
  `mccf_chorus.py`'s `fire_chorus()` never wired together) — confirmed
  still unresolved, not new, likely a real contributor to "dialogs out
  of order." Also confirmed: `dispatcher.js`'s `fireArcComplete()` has
  zero callers anywhere across the Loader, events editor, or composer,
  and `dispatcher.js` itself isn't loaded via `<script src>` in any of
  the four HTML files this session has — fully built, currently
  disconnected from everything. Both are real, scoped follow-ups, not
  evidence the events-editor UI itself needs replacing — nothing that's
  broken here lives in that UI at all.

  Verified via the `html.parser`-based check (2 `<script>` elements as
  expected — CDN include + main block — main block reads complete and
  un-truncated) and `node --check`. **Not verified live** — this is a
  genuinely larger, more interconnected change than anything else this
  session, touching six functions across the playback pipeline, and
  needs real testing with an actual two-path scene before being
  trusted the way the smaller fixes already are.
- ✅ **Multi-path fix confirmed working live — fired correctly in
  order.** Two more genuine gaps found and fixed while testing it (see
  below), one confirmed cause found for "moved but didn't walk," one
  new race condition found and fixed in a completely different part of
  the composer (Events Editor scene-data handoff).
  - **`_wirePathTimerBehavior` — missed in the original audit, found by
    testing.** Called from *inside* `pbActivateX3DTimers`, not as a
    sibling, so the earlier "map every call site" pass didn't catch it.
    It probes `Timer_{agent}_1` through `_8` bare — for group 2 this
    found group 1's now-dead leftover node instead of the real,
    running `Timer_Cindy_2_1`, wiring the walk/idle switching to a node
    that would never fire again (the interpolator still moved the
    avatar correctly — that ROUTE was already fixed — but nothing told
    it to animate the walk). Fixed, plus its callback-registration keys
    (would have silently failed to wire even with the name fixed,
    since X_ITE ignores `addFieldCallback` on an already-used key).
    A genuinely exhaustive re-sweep (every `Timer_`/`Arrival_`/`Dwell_`/
    `Kill_` construction in the file, not just remembered ones) found
    three more real instances: two fallback time-estimation lookups in
    `_x3dNow()`, and `pbStopX3DTimers`/`_pbResetViaKillScript` — these
    needed different treatment since "stop" and "reset" should sweep
    *all* of an agent's paths, not just the current one; reset
    specifically only repositions via order 1's script (avoiding
    ambiguity about whose start position should win) while still
    stopping any other order's leftover running timer.
  - **Events Editor scene-data race — a different bug, unrelated to
    the playback pipeline, found from the author's own console log.**
    `_sendSceneDataToEventsEditor()` fires based on whether the events
    editor *iframe* has loaded, completely independent of whether the
    scene's own waypoints/zones/paths/networks have finished loading —
    those only finish populating when `_restoreChorusFromXml`'s
    separate, later fetch resolves. Opening the Events tab in that gap
    snapshot whatever had been parsed so far (confirmed: 3 of 4
    waypoints in a real test, correct only after a full page reload
    gave the load time to finish by chance). A second, compounding gap
    in the same area: cues were sent to the Events Editor exactly once,
    unconditionally, from inside `_restoreChorusFromXml` — if the
    events iframe wasn't open/listening at that exact moment, the
    message was lost with nothing to re-send it later, unlike scene
    data which already re-sends on every tab-open.

    Fixed both: a `_sceneLoadInFlight` flag (set at load start, cleared
    on every exit path — success, missing raw XML, and both fetch
    failures, so it can never get stuck true) makes
    `_sendSceneDataToEventsEditor()` skip sending mid-load rather than
    ship a partial snapshot — `_restoreChorusFromXml`'s own existing
    re-send at its completion still delivers the correct, complete data
    a moment later. Cues are now cached (`_lastRestoredTracks`) and
    folded into that same re-send function, so every existing call site
    (tab-open, iframe-load, scene-restore-completion) automatically
    re-sends current cues too, rather than needing five call sites kept
    in sync by hand.
- ✅ **`garden_001.x3d` 404 on load — confirmed the author's own
  diagnosis and fixed.** A leftover placeholder from an earlier version
  of the tool, hardcoded in three places (`sc-name` input's default
  value, `sceneConfig`'s initial state; a third, harmless occurrence is
  just an illustrative example in a `mccf_chorus.py` docstring, not
  live code). The real bug: `_buildSceneData()` *guessed* an X3D URL
  from `sceneConfig.name` whenever no real export had happened yet
  (`_lastX3dUrl` unset) — on a fresh page load this fabricated and sent
  a URL to a file that has never existed, which the Events Editor then
  dutifully tried to fetch and 404'd on. Fixed by removing the guess
  entirely — `x3dUrl` is now only ever a confirmed export path, or
  empty; checked every other `sceneConfig.name` usage in the file first
  to confirm none of them share this "guess at load time" pattern
  (they're all tied to explicit user actions or naming *new* output
  files, not fetching an assumed-existing one).
- ✅ **WP1 never firing any EventCue — confirmed as a real, structural
  bug via the author's own testing, and fixed.** The EventCues-firing
  logic only ever lived inside `pbStepSession()`, called only on
  segment *completion* (WP2 onward). WP1 is displayed through a
  separate, direct `pbUpdateDisplay()` call in four different places
  (Play-All's grouped and fallback paths, `pbPlay`'s X3D-driven and
  JS-lerp paths) — none of which included that logic at all, so no
  camera or other EventCue could structurally ever fire on a WP1
  arrival, in any scene, ever. Extracted the logic into a shared
  `_fireWpArrivalEventCues()` helper and added the missing call at all
  four WP1 sites, plus consolidated `pbStep()`'s own separately-drifted
  duplicate copy into the same helper so this class of bug (working
  logic copy-pasted once, then silently diverging) is less likely to
  recur. Checked `pbStop`/`pbReset`/`pbPollState`'s own
  `pbUpdateDisplay` calls too — correctly left untouched, since firing
  cues from a passive state-refresh poll would cause repeated re-firing
  on every poll tick, and Stop/Reset shouldn't trigger new cue actions
  at all.

  **A real mistake made and caught during this fix, worth keeping in
  the record:** the helper-extraction edit matched only
  `function pbStepSession(sessionId) {`, missing that the real text was
  `async function pbStepSession(sessionId) {` — the insertion landed
  between `async` and `function`, silently stripping `async` from the
  function and leaving it dangling as a bare, invalid statement. This
  would have broken the entire script (a bare `await` outside an async
  function is a hard syntax error) had it shipped. Caught by re-running
  the established `html.parser`+`node --check` verification rather than
  assuming the edit was clean, and fixed properly. Final file reverified
  syntactically valid in full before delivery.
- ✅ **WP4 confirmed by the author as an authoring error, not a bug.**
  The cue's trigger was set to `manual` instead of the waypoint-arrival
  trigger; fired correctly once corrected. Consistent with what the
  code read showed at the time: the trigger *check* ran normally for
  WP4 (unlike WP1's total structural absence), and the matching logic
  is a plain, correctly-implemented case-insensitive string comparison
  — there was never a code-level reason to suspect WP4 specifically.
- ✅ **WP1 fix confirmed firing correctly.** The earlier retest that
  showed no change was the stale-file/cache explanation, not a second
  bug — confirmed by the line-number evidence (a ~5-line offset
  matching the fix's own size) and now by a clean retest showing it
  actually fire. `_fireWpArrivalEventCues()` now correctly runs for
  WP1 across all four display paths (Play-All grouped and fallback,
  `pbPlay` X3D-driven and JS-lerp), same as any other waypoint arrival.
- ✅ **A second, more consequential root cause for "camera moves
  slightly but never reaches its first position" found and fixed —
  the same `getField().setValue()` unreliability class as the very
  first fix of this entire session, but in a place that first fix
  never touched.** The Day 77 session's opening fix corrected this
  exact pattern only in the *events editor's preview* code
  (`mccf_events_editor_prototype_2.html`) — never in
  `mccf_x3d_loader.html`, the file that actually fires cues at runtime.
  Found by tracing the author's own report precisely: the `agent_orbit`
  cue's log stopped at `"agent_orbit started — subject=..."` with
  nothing further, and the code immediately before that log line writes
  `orbitProto.getField('initialTranslation').setValue(...)` — the exact
  same unreliable pattern, with every *other* field in the same
  function (`cycleInterval`, `loop`, the `keyValue`/`oriKeyValue` array
  writes) already correctly using direct assignment. `set_bind` would
  still correctly switch which viewpoint is bound, but the camera's
  starting pose could silently fail to register — explaining "moves
  slightly" (the keyframe animation still runs once `enabled=true`
  fires) but never visibly *arriving* at the authored starting shot.

  A full sweep found the identical pattern in **four** places, not
  just the one that surfaced it: `agent_orbit`'s and `agent_track`'s
  `initialTranslation`/`initialRotation` writes (`_executeAgentOrbit`/
  `_executeAgentTrack`), and — more surprising — the *static* free-
  camera shot's `CAM_Free_Transform` translation/rotation writes
  (`_executeStaticCameraShot`) and the *move*-shot's snap-to-start
  writes, both already flagged in this session as the mechanism behind
  the shot-type formula being retired, but still live code today. The
  static-shot site had an existing try/catch fallback to direct
  assignment — but only triggered on a thrown exception, which doesn't
  guard against the actual documented failure mode (a silent no-op,
  no exception at all) — so it would report "written OK" even on a
  write that never really took. The move-shot site sat two lines below
  a comment explicitly claiming *"direct property assignment
  throughout (confirmed working pattern)"* — these two lines were
  simply missed when that fix was made. All four now use plain direct
  assignment, no fallback needed, matching the pattern already proven
  everywhere else in this file.

  Four more occurrences of the same pattern found in a completely
  separate subsystem (`SoundFader_` audio-gain nodes) — left untouched,
  since there's no reported audio symptom right now and touching
  unrelated code without a reported failure risks unintended side
  effects. Worth checking first if any audio-cue reliability issue ever
  comes up.

  Confirmed live: `agent_orbit` now correctly snaps to and starts
  from its authored position at cue-fire (WP4), rather than drifting in
  from a stale one — the `initialTranslation`/`initialRotation` fix
  above is genuinely working, not just theoretically correct. This also
  likely explains camera-cue unreliability seen earlier in this session
  that was provisionally attributed to other causes, not just this
  specific `agent_orbit` report.

  **One authoring-model point worth recording, raised by the author
  while confirming this:** non-parented (placed) cameras — `medium`/
  `closeup`/`wide`/free — deliberately do not follow the avatar; only
  parented cameras (`agent_orbit`/`agent_track`, Character-Creator-
  authored, attached to the avatar's Transform) do. Not a limitation —
  this is the actual placed-vs-parented model this whole session's
  camera revision settled on (§1). Worth keeping in mind for future
  authoring confusion: a placed camera staying fixed while the avatar
  walks out of frame is correct behavior, not a bug to chase.
- ✅ **Media directory paths (music/soundeffects/convolver dropdowns) —
  fixed on both sides.** Not camera-related, but raised and closed in
  this same stretch. Root cause, confirmed precisely against
  `mccf_api.py`: `/media/list`'s directory was hardcoded as
  `static/x3d/media`, missing the `X3DAssets` segment the author's own
  directory reorganization added — should be
  `static/x3d/X3DAssets/media`. Fixed there, and separately in
  `mccf_scene_composer.html`, where all three dropdowns (music,
  convolver, soundeffects) wrote `media/{file}` as the URL baked into
  exported scenes — fixing only the server side would have left
  dropdowns showing correct filenames while exported scenes still
  pointed at the old, now-empty location. Checked whether the Loader
  itself references `media/` paths directly — it doesn't; it only
  plays back whatever URL Composer already baked in, so needed no
  separate fix. Not yet tested live.
- ✅ **`agent_orbit`/`agent_track` folded into `SHOT_ATTACHED` in
  `mccf_events_editor_prototype_2.html` — done, more involved than
  originally scoped.** The original two-step plan (add to
  `SHOT_ATTACHED`, remove `agent_orbit`'s framing fields) missed a
  whole dedicated framing-field code path for `agent_track` — a
  separate `isAgentTrack` flag, not gated by `SHOT_ATTACHED` at all,
  rendering its own lateral-offset/depth/height/v-angle sliders.
  Changed: `SHOT_ATTACHED` itself; the preview canvas's attached-shot
  label (was a hardcoded `agent_eye ? 'EYE' : 'SIDE'` ternary that
  would have mislabeled orbit/track as "SIDE"); removed the dedicated
  `agent_track` framing block entirely; fixed the "attached" inspector
  message, previously hardcoded for eye/side's `VP_{subject}_Eye/Side`
  binding pattern — now correctly describes orbit/track's different
  bound node family (`CAM_OrbitProto_{subject}`/`CAM_TrackProto_
  {subject}`) and notes their framing/loop lives in Character Creator
  now; removed `agent_orbit` from the loop-checkbox condition (baked
  in CC now, not per-cue) while leaving the unrelated, still-live
  free-form `orbit` shot type's own loop checkbox untouched.

  **Left alone, flagged not done, not a UI concern:** the cue data
  model still stores/exports `trackOffset`/`trackOffsetEnd`/
  `trackDepth` on `agent_track` cues (`applyShotPreset`, XML export)
  even though nothing reads them at runtime anymore — harmless dead
  metadata, not touched without auditing further first. Not yet tested
  live.

---

## 1. The new camera model

**The organizing question is no longer "what shot type is this," it's
"does this camera's position ever depend on a subject's live position at
cue-fire time."** Exactly one class of camera needs that: parented. Every
other camera — however it's framed, however it moves — gets its position
from the scene graph itself, authored ahead of time, not computed at fire
time.

### Placed (non-parented)

Authored in the **Place grid** (Place tab), by placing a camera and
either leaving it static or attaching authored motion to it.

- **Static placed camera.** Fixed transform, set once at placement time.
  Wide/Medium/Closeup/Over-Shoulder/Two-Shot/Profile/etc. are no longer
  live-computed formulas — they're just placed cameras with descriptive
  names. This is functionally identical to the *existing* `free_camera`
  cue type (*"position/orientation are fixed at placement time in
  Composer's grid UI... no framing sliders: there's nothing here for
  them to adjust"*) — that code path was already correct for this job;
  the static/relational shot-type formula path duplicated it badly.
  Events' only job for these is bind/fire — select which placed camera
  activates, no framing math involved at all.

  **Naming, settled Day 77:** shot-type labels persist as identity, not
  as live computation — but a scene can have multiple instances of the
  same shot type (two separate Closeups on different subjects, say), so
  each placed instance is labeled with its shot type *plus an instance
  number* (`Closeup_1`, `Closeup_2`, ...), unique per scene, used as the
  DEF name in routes/scripts and as the display label on the Place grid.
  This extends the existing `registerId()` uniqueness guard (Day 72 —
  refuses a name collision outright rather than silently overwriting)
  rather than replacing it: `registerId()` still enforces the collision
  refusal, but camera placement now needs to *generate* the next
  available number for a given shot-type label automatically, rather
  than requiring the author to hand-pick a unique name each time.

  **Seeding, settled Day 77:** choosing a shot-type label at placement
  time *does* pre-fill the `SHOT_PRESETS` distance/height/angle (and now
  roll, see below) numbers as a starting transform — the author then
  drags/dials it into its final position from there, rather than
  starting from a neutral default. `SHOT_PRESETS` keeps a real job under
  the new model: seed values at placement time, not a live per-cue
  formula.

  **Orientation control, settled Day 77:** placing and pointing a static
  camera needs yaw, pitch, *and* roll — roll being rotation about the
  camera's local **Z axis (the look/forward axis)**, distinct from yaw
  (world Y) and pitch (world X). Yaw/pitch already exist and are already
  confirmed working — the Place→Cameras edit panel's `cam-hangle`/
  `cam-vangle` sliders (feeding `placedCameras[name].hAngle`/`.vAngle`)
  are exactly this, per the item-1 in-browser test earlier this session.
  **Roll is a real, scoped gap, not a new idea:** it already exists as a
  concept — `cue.roll`, currently gated to only appear in the events
  editor inspector when `isDutch` is true, and it already round-trips
  through the composer's XML restore (`roll: gf('roll')`) — but it was
  never added to the Place→Cameras *placement* form itself, because
  under the old model Dutch's roll was a live per-cue formula input, not
  a placement-time property. Under the new model it needs to move: a
  third slider (`cam-roll`, alongside `cam-hangle`/`cam-vangle`) on every
  placed camera's edit panel, not just Dutch, feeding into
  `placedCameras[name].roll` and threaded through `buildFreeCamerasX3D()`'s
  export (which today only emits `yaw`/`pitch` on `<FreeCamera>`, no
  roll attribute at all).

  **Dependency, confirmed Day 77 (`mccf_camera_protos.x3d` now in hand):**
  `yaw`/`pitch` are composed as two *nested* `Transform`s, not two
  independent fields on one node — outer `Transform DEF="YawXform"`
  holds world position and rotates about world Y; inner
  `Transform DEF="PitchXform"`, its *child*, rotates about its own local
  X (already yaw-rotated by the nesting), with the `Viewpoint` inside
  that. Roll needs to follow the same pattern one level deeper: a third
  `Transform` nested inside `PitchXform`, rotating about local Z, with
  the `Viewpoint` moved to be its child. Yaw→pitch→roll, innermost-last —
  not a new composition scheme, just extending the one already there.

  **A more foundational gap, surfaced while confirming this:** the
  `FreeCamera` proto's own Day 64 comment states plainly — *"Binding/
  triggering a placed free camera during playback... is NOT wired yet —
  this proto only covers placement + export."* The events editor's
  `free_camera` cue code agrees from the other side: *"Only `cue.camera`
  matters to the Loader"* — meaning the Loader is where actual runtime
  bind/fire would have to happen, and that file (`mccf_x3d_loader.html`)
  has never been in hand this session or last. **This is a real
  precondition for the whole placed-camera model above**, not a detail:
  if runtime bind/fire genuinely was never wired past Day 64's
  placement-only proto, then every static/relational shot type moving to
  "just a placed camera + a bind cue" is currently unplayable at
  runtime, not merely unrefined. Needs confirming before further design
  goes on top of it — see open items.
- **Animated placed camera** (Dolly, Pan, Orbit, Crane, Track, etc.).
  Also placed in the Place grid to get a starting transform, but with
  motion **authored, not computed** — cycle interval, distance, angle,
  orientation (including off-axis roll/skew), baked into the scene graph
  as `PositionInterpolator`/`OrientationInterpolator`/`TimeSensor` nodes
  at export time, the same way `buildInterpNodes()` already bakes agent
  Paths. Per-type edit surfaces (author-facing tabs, not live sliders)
  needed for at least:
  - **Agent orbit** (distance from center = the avatar) — mostly already
    exists as the `AgentOrbitCamera` proto in `mccf_camera_protos.x3d`;
    this is a parented case, see below, but shares the orbit-authoring
    field set.
  - **Scene orbit** (distance from an arbitrary scene point, not an
    avatar) — narrow/wide, varying height. No existing proto covers
    this; this is new authoring surface in the Place module.
  - Dolly/Pan/Crane/Track — same authored-parameter shape, straight-line
    or simple-path motion rather than orbital.
  Events' job for these is the same as static: start/enable the already-
  baked `TimeSensor` on cue-fire. No SAI-computed motion, live or
  otherwise.

### Parented

Authored in **Character Creator**, per avatar file, per the Avatar Camera
Rig decision (`MCCF_Avatar_Camera_Rig_Manifest_Spec_v0.1.md`). Travels
with the actor, so it's always correctly framed regardless of when the
cue fires — this is the one case where "is the actor in position yet"
genuinely doesn't matter, structurally, not by author discipline. Any
shot concept — including orbit/track motion — can be authored here
instead of as a placed camera, when travelling-with-the-actor is what's
wanted. `AgentOrbitCamera`/`AgentTrackCamera` protos already implement
this pattern for orbit/track specifically.

**Split of responsibility, settled Day 77:** Character Creator owns the
rig and its initial position — radius/height/start-angle for an orbit,
the rig's attach point, anything that defines *what the camera is and
where it begins*. The Events Editor keeps everything else — trigger,
loop/duration, play timing — the performance layer, not the rig
definition. Concretely: `agent_orbit` and `agent_track` should join
`agent_eye`/`agent_side` as fully `SHOT_ATTACHED` in the events editor.
Today `agent_orbit` is deliberately excluded from `SHOT_ATTACHED` because
it currently carries its own framing fields (radius/height/start angle)
in the Events inspector — that per-cue framing authoring moves to
Character Creator under this split, and Events' job for all four
attached shot types becomes identical: bind the named rig, fire it, own
loop/duration. No framing fields for any parented shot type in the
Events inspector once this lands.

### What the author is responsible for

For every placed (non-parented) camera, static or animated: the actor
must be in the correct position when the camera's cue fires. This is
authorial responsibility, not something the system enforces or computes
around — consistent with how Path/Waypoint triggers already work
elsewhere in the composer.

---

## 2. What this retires

- `_prevComputeCamPos()` / `_prevLookAtOrientation()` in the events
  editor, and the equivalent in the Loader — the subject-relative offset
  formula. These become **dead code for camera positioning** once the
  Place-grid placement path replaces the static/relational shot types.
  They may still have a narrow second life as placement-time *assist*
  (pre-filling a reasonable starting position when an author picks
  "Close-Up" in the Place grid, which they then hand-adjust and lock in)
  — settled: they seed a starting transform at placement time (§1),
  authored from there, not deleted outright. The item-1 preview fix
  earlier this session touched this exact function in the events
  editor; it has no further job to do there once static shots route
  through placed cameras (§3's shell) instead.
- `SHOT_TYPES`/`SHOT_PRESETS`'s `static` and `relational` groups (Wide,
  Medium, Closeup, Extreme Closeup, Overhead, Worm's Eye, Dutch, Over
  Shoulder, Profile, Two Shot) as a *live mechanism*. The `move` group
  (Dolly In/Out, Pan, Tilt, Orbit, Crane Up, Track) is **not** retired —
  it keeps real work, just baked instead of computed (§1).
- The three-class framing in `MCCF_Camera_System_Spec_v1_3.md`. Needs a
  revision pass — not yet written.
- `agent_orbit`'s per-cue framing fields (radius/height/start angle) in
  the events editor inspector, and its exclusion from `SHOT_ATTACHED`
  (line ~876, with its own comment explaining the exclusion). Both
  retired by the Character-Creator/Events split above: `agent_orbit`
  becomes a fourth fully-`SHOT_ATTACHED` type alongside `agent_eye`/
  `agent_side`/`agent_track`, rig framing moves to Character Creator,
  Events keeps only trigger/loop/duration for it.

## 3. Place Editor shell — generic across proto families, Cameras first

**Settled Day 77, generalized from an initial camera-only framing.** The
shell isn't a Cameras-specific rebuild — it's the **Place Editor**,
extending Day 76's Scene Placement Module Consolidation decision (§2 of
that doc: Lights/FX/assets join the same Place module as additional
sub-tabs, sharing grid/select/move/query and a type-appropriate
inspector, "not a bespoke one per type"). What's new here is specifically
the **live X_ITE center pane** as part of that shared shell — and that
pane earns its place only for proto families with something optical to
actually look at. Cameras first; Lights whenever their spec lands: same
shell, different proto family, different edit-tab fields. Zones/
Waypoints/Paths don't get it, per §4 — nothing to look at.

The current 2D-grid-only Place→Cameras panel — free-camera-only, no live
preview — is retired, replaced by this shell's Cameras sub-tab.

**Built natively in `mccf_scene_composer.html`, not shared with the
events editor file.** Once Events' camera surface shrinks to picker +
trigger + timing (per the Character-Creator/Events split and the
`free_camera` cue path already doing that job correctly), Place and
Events are genuinely different-sized jobs, not the same UI wearing two
hats. Place borrows the *patterns* already proven in
`mccf_events_editor_prototype_2.html` — `loadX3DViewport()`'s load/
teardown handling, `_bindFreeCamera`-style bind-on-select — rather than
sharing the file. Events keeps its own X_ITE viewport too, for a
different reason: general timeline/scene playback preview across all cue
types, not camera-specific framing.

**Open caveat, stated plainly:** this is a design bet, not a proven one.
Whether a shared grid+X_ITE+edit-tab shell across multiple proto
families is actually efficient to build and use only becomes clear once
Cameras is implemented and tested — not before. Worth revisiting after
that first pass, not assuming it generalizes cleanly to Lights/FX sight
unseen.

- **Left (grid):** shows every placed object of the active sub-tab's
  type — for Cameras, every placed camera, static and animated alike.
- **Center (X_ITE):** live view. Selecting an object binds X_ITE to
  *that object's own viewpoint* — look-through-the-lens, not an
  orbit/overview of the object from outside. For a placed camera this
  reuses the binding machinery already confirmed working this session
  (`_bindFreeCamera` for statics; the animated-placed-camera bind path
  from item 8/§5 once it exists for motion cameras).
- **Right (edit tab):** opens on selection, exposes every active
  parameter for that object's type — position, yaw/pitch/roll for a
  static camera; cycle interval/distance/angle/orientation for an
  animated one, once §1's field design lands. Field set varies per proto
  family; the shell mechanics (select, drag, live-link) don't.
- **Grid ↔ edit tab are live-linked both ways:** dragging an object in
  the grid updates its X/Z live; adjusting the edit tab's fields (or
  selecting a different object) updates the grid and the X_ITE view to
  match.

This directly answers the "look through the lens vs. look at it from
outside" question raised earlier this session: it's look-through-the-
lens. And it makes the item-1 preview-fix and `loadX3DViewport()`
teardown work from earlier this session load-bearing rather than
incidental — a live center-pane view tied to selection is exactly the
machinery that fix protects.

**Scope note:** this is the Cameras sub-tab's shell first, not a full
Place-module rebuild in one pass. Whether Zones/Waypoints/Paths move
onto this same shell or stay on the current 2D-grid-only one is settled
— see §4.

## 4. Settled: Zones/Waypoints/Paths stay on the current shell

**Decided Day 77.** They do not move onto the new three-pane Cameras
shell. Reasoning: the new shell's defining value — a live X_ITE view
tied to selection — only pays for itself for objects with an optical
output (cameras now, lights later); zones and waypoints are purely
2D-positional and the existing grid-only shell already represents that
correctly. Moving them now would also be a second scope expansion on
top of everything else this session already added to "V1 is
camera-only." The one real benefit a move would bring — consistent
select→edit-tab behavior instead of today's inconsistent right panels
(the `clearSel()` workaround Day 76 flagged as a confirmed real problem)
— doesn't require the X_ITE pane and can be delivered to the existing
Zones/Waypoints/Paths shell independently, later, without waiting on or
being bundled into the Cameras rebuild. Revisit only if Lights' eventual
arrival changes the calculus.

## 5. Open items for Day 78, ranked

**Confirmed done this session, kept brief since the banner has the full
detail:** multi-path playback orchestration (1), Loader binding /
`_bindFreeCamera` (2), seeding/auto-numbering (3), Character Creator
camera rig including `agent_orbit`/`agent_track` binding (4), the
`getField().setValue()` fixes across all four runtime camera-firing
sites (5), WP1 EventCues (6), `garden_001.x3d` (7), media directory
paths — code fixed, not yet tested live (8).

**Deprioritized per the author's own status update, not dropped:**
wiring `PlaybackManager.chorus_callback` — the old Chorus mechanism is
firing fine as things stand, no problem yet. Worth returning to when it
actually becomes a blocker.
- ✅ **`dispatcher.js`'s loading location — resolved.** The earlier
  "zero callers anywhere" finding was checking the wrong files.
  `mccf_timeline_dialogue_prototype_v2.html` — a genuinely new "Actor
  Timeline / Dialogue Editor" the author shared, separate from
  everything else in this session — loads it directly via
  `<script src="js/dispatcher.js">`, alongside `field-map.js`,
  `timeline-xml.js`, `dialogue-xml.js`, and `worked-manifests.js`. This
  is the tool it was built for.

  **What this tool actually is, surveyed but not yet deeply audited:**
  a richer authoring model than the old events editor — every step has
  a *structured* trigger object (`scene-start`/`touch`/`zone`/`sensed`/
  `declared`, not a flat `"{wp} arrive"` string), a `verb` (`start`/
  `stop`/`arrived`/`blocked`/`set`), and `durationKind` (`fixed` vs
  `estimate`). It already has its own **camera authoring track** —
  `id:'cuts', label:'Camera cuts', kind:'camera'` under an actor typed
  `Director` — with `cameraType`: `fixed`/`track`/`orbit`/`pov`/
  `dolly`, plus `targetActor`/`viewpointRef` fields, driven by the same
  structured-trigger system as every other track.

  **Day 78 correction — the "shell vs. timeline tool" question below
  was wrong, not just unresolved. It had already been answered, in
  three Day 75/76 spec docs the author provided that this session
  didn't have.** `MCCF_Scene_Integration_Spec_v0.1.md` §2 settles
  exactly this: `cameraType` should map onto `ProtoInstance` selections
  against the *existing* proto library
  (`AgentOrbitCamera`/`AgentTrackCamera`/`FreeCamera` in
  `mccf_camera_protos.x3d`) — confirmed directly today, not just cited:
  the proto names match the old events editor's `agent_orbit`/
  `agent_track` shot-type names exactly. The Timeline tool doesn't get
  a parallel camera-positioning mechanism; positioning happens in the
  grid/Place system, the Timeline authors *when* a cut to an
  already-positioned camera fires. There was no fork to resolve.

  **What this means for this whole session's camera work:** it isn't
  parallel or potentially-redundant to a "V5" migration — it's
  `MCCF_Scene_Integration_Spec_v0.1.md` §6's own recommended *first*
  module in the migration's module-by-module order, already executed:
  "Camera — most prior art already exists across three sources, likely
  the fastest to actually consolidate" (item 1), and "Character Creator
  + avatar PROTO structure — needed to confirm the parented-camera-in-
  proto hypothesis" (item 3) — the hypothesis being the author's own
  remark, recorded in that spec, that *"avatars have parented cameras
  as defaults in their protos."* Today's Character Creator camera-rig
  chain isn't just consistent with that hypothesis — it's the actual
  mechanism that makes it true.

  **What the same spec also settles, retroactively affecting earlier
  work this session:** the old events editor's embedded X_ITE preview
  and left-pane grid camera-positioning UI are explicitly being
  retired — *"the preview caused tab crashes, the grid editor was not
  very functional."* The SAI write-path fix made to that preview at the
  very start of this session was a real fix to real code, but it's
  fixing something already on its way out, not something to keep
  investing in going forward.

  **What's genuinely still open, per these docs, not invented this
  session:**
  - `MCCF_Scene_Integration_Spec_v0.1.md` §4 — Actor/Agent
    reconciliation. Explicitly called "the single largest open
    data-model question blocking real integration work," and should be
    resolved before any generator code is written. `placedAgents` has
    no concept of tracks, field maps, or the non-avatar Actor types the
    schema already needs (`SceneFog`/`Door`/`Camera`/`Audio`/`Movie`).
  - `MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md` §4a — confirms,
    independently of this session's own finding, that `dispatcher.js`'s
    `fireArcComplete()` and `mccf_chorus.py`'s `fire_chorus()` are
    still not wired together. Good cross-confirmation this session's
    read was correct; still real, scoped, undone work either way.
  - The actual native-X3D generator — compiling Track/Step/Cue XML into
    `TimeSensor`/`Interpolator`/`ROUTE`/generated `<Script>` nodes,
    using `dispatcher.js`'s verb/trigger/collision/blend semantics as
    the spec that generator reproduces, not a file that ships at
    runtime (per §1's central decision — the same pattern the existing
    `SoundFader_*` Script generation already proves works). This is the
    real "V5" build; nothing in this session started it.
  - `mccf_timeline_dialogue_prototype_v2.html` stays as the authoring/
    preview tool even after the generator exists — §7 confirms it's
    "not being deprecated by this integration," and separately confirms
    both its tabs are "fully functional and verified," resolving the
    prototype-flag-vs-comment inconsistency flagged just above as
    exactly what the inline comment claimed, not the stale UI label.

**Actually open and actionable, ranked:**

1. **`MCCF_Scene_Integration_Spec_v0.1.md` §4 — Actor/Agent
   reconciliation.** Not invented this session — the spec's own words:
   "the single largest open data-model question blocking real
   integration work," and should be resolved before any generator code
   is written. `placedAgents` today has no concept of tracks, field
   maps, or trigger-driven behavior; the non-avatar Actor types the
   schema already needs (`SceneFog`/`Door`/`Camera`/`Audio`/`Movie`)
   have no equivalent in composer's data model at all. Does Track/Step
   data attach directly onto `placedAgents` entries, with a new,
   parallel entity for non-avatar Actors — or is there a unifying
   "Actor" layer above both that composer doesn't have yet? This is
   the real next item, not the shell question this list previously
   (wrongly) led with.
2. **Wire `dispatcher.js`'s `fireArcComplete()` to `mccf_chorus.py`'s
   `fire_chorus()`.** Confirmed independently twice now — this
   session's own read, and `MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md`
   §4a. Real, scoped work, not a design question. Still sitting exactly
   where Day 76 first flagged it.
3. **The native-X3D generator itself** — compiling Track/Step/Cue XML
   into `TimeSensor`/`Interpolator`/`ROUTE`/generated `<Script>` nodes,
   with `dispatcher.js`'s verb/trigger/collision/blend semantics as the
   spec that generator reproduces rather than a file that ships at
   runtime. The `SoundFader_*` Script-generation pattern already proves
   this approach works in this exact codebase; nothing has extended it
   to Track/Step data yet. This is the real "V5" build. Blocked on (1)
   — no point generating code against an Actor model that doesn't exist
   yet.
4. **Camera's own remaining piece: does `cameraType`'s `fixed`/`dolly`
   values need genuinely new authoring surface, or does grid placement
   already cover them?** Per the Scene Integration Spec §2, `cameraType`
   maps onto the existing proto library — `orbit`/`track`/`pov` map
   cleanly onto `AgentOrbitCamera`/`AgentTrackCamera`/eye-side (all
   confirmed working this session). `fixed` and `dolly` are closer to
   this session's placed-static and placed-animated categories — the
   remaining open piece is field-layout design for the animated case
   (Scene Orbit, Dolly/Pan/Crane/Track as Place-grid-authored, baked-
   interpolator motion), not a new camera *architecture*. Natural home
   is wherever grid/Place authoring ends up living once (1) is
   resolved, since Actor reconciliation likely reshapes what "the grid"
   even is.
5. **`MCCF_Camera_System_Spec_v1_3.md` revision pass** — replace the
   stale three-class model with the placed/parented split this session
   settled (§1). Documentation only, no code risk, can happen anytime.
6. **Confirm the events editor teardown fix in-browser.** Delivered
   this session, never tested — worth doing, but per the Scene
   Integration Spec §2 this whole preview/grid UI is being retired
   regardless, so this is about not leaving known-broken behavior in
   place during the transition, not a long-term investment.
7. Everything from the Day 76 seed's own §3 not otherwise closed above
   (character-voice prompt builder, lighting research pass — also
   explicitly last in the Scene Integration Spec's own module order,
   §6 item 6 — right-panel standardization shape) is unchanged and
   still open, no new urgency signaled either way.
