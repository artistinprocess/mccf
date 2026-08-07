# MCCF Day 83 Seed — For Day 84

**Status: lighting/camera property parity closed out, a real native camera
fly-transition built, and a genuine multi-file gesture-dropdown bug chased
to ground across four files. One more real bug found and partially fixed
(EventCues export sourcing the wrong, dead variable) — deliberately left
mid-fix and scoped back, because it steps into X3D Export/Loader territory
that's gated behind the Dialogue/master-clock design session. That session
is next.**

---

## 1. What happened this session, in order

1. **Light property parity in Place** (item 2 from the Day 82 list). Full
   optical property set — `on`/`color`/`intensity`/`ambientIntensity`/
   `attenuation`/`radius`/`cutOffAngle`/`beamWidth` — added to the Place
   tab's light form, storage, `buildLightsX3D()` export, and scene
   save/load persistence, filtered per type to match each proto's real
   field set (`mccf_light_protos.x3d` already had these fields declared;
   only the Composer side was missing). Backward-compatible defaulting for
   lights placed before this session.

2. **Camera cinematic properties**, at the user's request to give cameras
   "as much cinematic expression as possible." Added `fieldOfView`,
   `nearDistance`, `farDistance`, `jump` to **all three** camera protos
   (`FreeCamera`, `AgentOrbitCamera`, `AgentTrackCamera`) in
   `mccf_camera_protos.x3d`, confirmed against X_ITE's real `Viewpoint`
   docs. Composer's Place form extended for `FreeCamera` only — Orbit/Track
   shots are Events-cue-authored, not Place-authored, so their copies of
   these same new fields aren't reachable from Composer; flagged as a real,
   separate gap for whenever the Events Editor's camera-cue authoring
   surface gets built out (see §5 below — turns out that's a bigger gap
   than expected).

   **Correction made mid-session, worth remembering**: `jump` was initially
   mislabeled as a "Hard Cut vs. Smooth Transition" toggle. Checked the
   real ISO/IEC 19775-1:2023 spec text directly (not X_ITE's paraphrase) —
   `jump=TRUE` (the real default) means instant snap; `jump=FALSE` means
   "the view remains unchanged" on bind, NOT an animated transition. The
   actual animated-transition mechanism is `NavigationInfo.transitionType`/
   `transitionTime`, a different node entirely, untouched this session.
   Relabeled the checkbox and every related comment to match the real
   semantics before it shipped confused.

3. **Real camera fly-transition, built from scratch.** The previous 'fly'
   transition (in `mccf_x3d_loader.html`'s `_bindNamedViewpoint`) just
   toggled `Viewpoint.jump=false` via SAI before binding — confirmed via
   the spec text in item 2 above that this doesn't animate anything at
   all; it was never functioning as a "fly," possibly ever.

   Built `_flyCameraTo()` — a genuine 2-keyframe `PositionInterpolator`/
   `OrientationInterpolator` animation, eased through a fixed cosine
   ease-in-out curve (`CAM_FlyEase`, a `ScalarInterpolator` with static,
   author-time-fixed key/keyValue — never touched by the Loader at
   runtime). Uses its **own dedicated vessel**
   (`CAM_FlyTimer`/`CAM_FlyEase`/`CAM_FlyPosInterp`/`CAM_FlyOriInterp`),
   deliberately separate from the existing move-shot vessel
   (`CAM_Timer`/`CAM_PosInterp`/`CAM_OriInterp`) so two `TimeSensor`s can
   never simultaneously fan into `CAM_Free_Transform`'s
   `set_translation`/`set_rotation`. Added to **both** of Composer's export
   code paths (confirmed there are two, kept in sync).

   FROM pose is read live via `MCCF_PathRecorderProx.position_changed`/
   `orientation_changed` — the same confirmed-working mechanism the
   Events Editor's own path recorder already uses, since
   `Viewpoint.position`/`orientation` only ever hold authored values, not
   live navigated pose, for any proto-wrapped camera type.

   Wired into two places: `_executeStaticCameraShot` (closeup/wide/etc. —
   destination pose already computed via `_lookAtOrientation`, the easy
   case) and the explicit named-viewpoint cue path (`VP_Overview`, zone
   VPs — plain top-level `Viewpoint` nodes, direct SAI field read).
   Deliberately **not** wired for `agent_eye`/`agent_side` (avatar-local,
   moving target) or `free_camera` (would require hand-combining
   yaw/pitch/roll into one axis-angle — exactly the custom rotation math
   this project's house style avoids). Both unsupported cases now log a
   clear diagnostic and fall back to cut, instead of silently doing
   nothing like before.

4. **Gesture-dropdown sanity check** (user noticed the Events Editor's
   Gesture cue dropdown only ever showed "Default") turned into a real,
   four-file bug hunt:
   - **`mccf_scene_composer.html`**: `placedAgents[name].behavior_clips`
     was never populated in three places — `placeAgentAt()` (new
     placement), both branches of the scene-XML-load path, and
     `loadAgents()` (runs on every Actors-tab visit / "Refresh from API,"
     far more often than `loadAll()`, which only runs once at startup).
     `_buildSceneData()`'s `agentClips` — what the dropdown actually reads
     — is built from `placedAgents`, not `agents`, so this was a real,
     confirmed sync gap, not a data-availability question. Fixed all
     three, guarded so none of them clobber already-good data.
   - **`mccf_character_creator.html`**: `saveCharacter()`'s payload never
     included `behavior_clips` at all. Fixed to send `_hePlaybackClips`
     (the real clips discovered server-side from the loaded H-Anim file)
     — deliberately **not** `_heClips` (a separate pose-authoring
     scratchpad that self-seeds with one hardcoded "Default" entry
     whenever empty, independent of what the file actually has).
   - **`mccf_hanim_api.py`**: `/hanim/export`'s handler was
     wholesale-replacing `cultivar_def.behavior_clips` with whatever was
     in that export's `clips[]` field — which is `_heClips` again (hand
     authored only), sent from a *different* button (`heExport()`, the
     H-Anim Editor's own "export →"). So every Export, even one that only
     changed skin/receptivity, silently wiped the cultivar's real clip
     table down to Default. Fixed to merge by name instead of replace.
     Confirmed `_write_clip_nodes` (the code that actually writes new
     `TimeSensor` nodes into the X3D file) has **no existing-DEF check** —
     merging real clips into that same field would have caused duplicate
     `TimeSensor` DEFs, invalid X3D. Deliberately left that function
     untouched; only the cultivar-table merge logic changed.
   - **Confirmed working end-to-end, live**: `cultivar_Cindy.xml` now
     round-trips all 8 real clips (Default/Pitch/Yaw/Roll/Walk/Run/Jump/
     Kick — the standard base-timer set every avatar in this system
     carries). Composer's "Refresh from API" (on the Actors tab) is what
     actually picks up a freshly-changed cultivar file — a plain page
     reload alone did **not** pick it up in testing; this needs its own
     look eventually (see §5).

5. **EventCues export bug**, found while investigating whether refreshing
   agent data wipes unsaved Events Editor edits:
   - The old "capture cues before tearing down the Events iframe" safety
     net (`mccf_request_cues`/`mccf_cue_data` reply) is dead code — the
     current Events Editor has no handler for it at all (retired along
     with the old Day-79 cue system).
   - `_doExportSceneXML`'s two call sites were sourcing cues from
     `_lastKnownEventTracks` — the same dead variable that reply mechanism
     was supposed to populate, and never does. The live, correct variable
     is `_lastTimelineCues`, populated by "Save to Composer"
     (`mccf_production_cues`). Confirmed by the user's own direct test:
     cue edits survive Composer tab switches (since `_lastTimelineCues` is
     a page-level variable, unaffected by the Events iframe being torn
     down and reloaded) but **not** a scene reload — because the exported/
     saved file's `<EventCues>` block was always empty, sourced from the
     wrong variable. Composer's own receiver for `mccf_production_cues`
     even self-documents this with a toast: *"Timeline cues saved (N).
     Not yet wired into X3D export."*
   - **Fixed**: both `_doExportSceneXML` call sites now source from
     `_lastTimelineCues.cues` instead. This part was kept — reasoned
     through with the user as a plain, scope-independent data-loss fix
     ("don't silently drop an author's saved work on reload"), not a step
     toward real X3D/Loader cue translation.
   - **Found but deliberately NOT fixed, stopped right at the edge**: the
     `<EventCues>` XML-writing block inside `_doExportSceneXML` still
     expects the *old*, retired nested shape (`{type, label,
     cues:[...]}` — grouped tracks containing cue arrays). The *current*
     `CUES` data (from `Save to Composer`) is a **flat** array of
     `{id, track, target, label, t0, duration, params}` objects. Even with
     the correct variable now feeding in, the writer's
     `_eventTracks.forEach(t => t.cues.forEach(...))` would find
     `track.cues` undefined on every flat cue object and silently write
     zero `<Cue>` elements — right data source, wrong shape. Rewriting
     this needs the real current field shapes, which surfaced one more
     finding:
   - **Also found**: of the five cue track types, only **Gesture** (real
     clip dropdown) and **Path** (real recorded-path dropdown) have a real
     authoring surface today. **Camera, Light, and Audio cues only expose
     Target + a generic free-text "Label" field** — none of the richer
     camera-cue schema (`shot`, `subject`, `transition`, `flyDuration`,
     `distance`, `height`, `hAngle`, `vAngle`, `roll`...) that the Loader's
     `_fireCameraEventCue`/`_flyCameraTo` know how to consume has *any*
     authoring UI in the current Events Editor at all. Practically: the
     fly-transition work from item 3 above has no way to be triggered by
     an author clicking through this tool yet — there's no button that
     sets `shot=` or `transition="fly"` anywhere.
   - Given all of this is squarely inside "Timeline cues → real X3D"
     (item 4 from the Day 82 list, explicitly gated behind the Dialogue/
     master-clock session), work stopped here. The variable-swap fix was
     kept; the writer-shape rewrite and the camera-cue authoring UI were
     **not** started, per direct instruction this session — "We weren't
     going to implement the X3D Export and Loader until we finished the
     dialogue editor."

6. **Non-code discussion, worth keeping in view for the Dialogue session**:
   - Analyzed a real Web3D/HAnim mailing-list thread about attaching
     `HAnimSite` landmarks to skin meshes (vertex-index vs. weighted
     correspondence vs. semantic/implementation separation). Connected it
     to this project's own confirmed history — Displacer never worked
     here, a custom XML solution was built instead — as real, concrete
     field evidence against leaning on Displacer as "tried and true"
     precedent. Distinguished the single-landmark-point problem in that
     thread from MCCF's actual whole-body Mixamo/Blender ingest distortion
     problem — related but not the same problem.
   - User experimented with Tripo3D (an "Enheduanna" avatar, ornate
     warrior model, ~1.88M faces/979K vertices — noted as far above
     real-time budget, worth decimating before ingest whenever this
     pipeline is actually used). Found real field evidence (a Medium
     writeup) of someone hitting the identical Tripo→Mixamo→Blender mesh-
     corruption symptom and resolving it with a specific export order:
     Tripo FBX → Mixamo FBX → Blender → GLB. Filed for whenever the
     Mixamo/Blender ingest problem comes off the backburner — not
     actioned this session.
   - User restated MCCF's core design thesis clearly, worth remembering
     verbatim in spirit: MCCF is a **semantic system**, not a generalized
     X3D editor — X3D has no nodes for EBPS or dialogue, those are
     deliberately layered in. Storage is kept as neutral/semantic XML
     (never X3D) specifically so it can be repurposed later (e.g. XSLT to
     shooting scripts), which is *why* X3D generation is one-way and
     never edited back. This directly explains why nearly every bug this
     session sat exactly at the seam between the semantic layer and the
     X3D layer, not cleanly inside either one — that seam is where two
     different vocabularies have to agree, and it concentrates bugs by
     design, in exchange for keeping the authoring surface writer-facing
     rather than X3D-node-facing.

---

## 2. Current file state

| File | Status |
|---|---|
| `mccf_scene_composer.html` | ✅ Light/camera property parity done. `placedAgents.behavior_clips` sync fixed (3 sites). `_doExportSceneXML`'s cue-source variable fixed (2 sites) — but the `<EventCues>` writer itself still expects the old nested shape; **not** rewritten this session. |
| `mccf_camera_protos.x3d` | ✅ `fieldOfView`/`nearDistance`/`farDistance`/`jump` added to all three protos, wired via `<IS>`. Well-formed, validated. |
| `mccf_light_protos.x3d` | Unchanged this session — already had the full field set Composer now exposes. |
| `mccf_x3d_loader.html` | ✅ `_flyCameraTo()` built — real, native, eased camera transitions. Wired for static shots + named viewpoints only; agent-attached and free-camera fly deliberately deferred with diagnostics. |
| `mccf_character_creator.html` | ✅ `saveCharacter()` now sends real `behavior_clips` from `_hePlaybackClips`. Diagnostic `console.log`s added (harmless to leave in). TODO comment corrected to reflect confirmed server-side API status. |
| `mccf_hanim_api.py` | ✅ `/hanim/export`'s cultivar `behavior_clips` update changed from replace to merge-by-name. `_write_clip_nodes` untouched (confirmed no existing-DEF check — do not feed it already-real clips). |
| `mccf_cultivar_lambda.py` | Unchanged — read for verification only. Confirmed `register()` does a hard full-replace with no merge, and `CultivarDefinition` has no fallback that fabricates clip data — useful to remember when debugging anything cultivar-shaped later. |
| `mccf_events_editor_prototype_2.html` | Unchanged this session — read extensively for verification. Confirmed: only Gesture/Path cues have real param authoring; Camera/Light/Audio are Target+Label-only; the `mccf_request_cues` reply path is dead; `exportProductionCues()`/`Save to Composer` → `mccf_production_cues` is the one real, live save path. |
| `mccf_api.py` | Unchanged. Confirmed `/cultivars/xml` is NOT here — owned by the blueprint in `mccf_cultivar_lambda.py`. Worth remembering so a future session doesn't look in the wrong file again. |

---

## 3. Immediate next steps

1. **Dialogue-editor / master-clock design session — this is next**, per
   direct instruction. Still exactly the open question the Day 82 seed
   named: does dialogue's clock-driven, audio-triggering behavior share a
   mechanism with the Audio track's cues, or does it need its own? This
   session surfaced two more things that should probably be brought into
   that same design conversation rather than solved separately, since
   they're the same "how do authored cues actually reach real X3D
   behavior" question:
   - The `<EventCues>` writer needs a real rewrite to match the current
     flat `CUES`/`params` shape (found this session, not fixed).
   - Camera/Light/Audio cues need a real authoring surface (shot type,
     subject, cut/fly, distance/height/angle for camera at minimum) —
     currently just Target+Label. Without this, nothing downstream
     (including this session's fly-transition work) is actually usable by
     an author yet.
2. **Recorded-path playback consumption** — still the one safe,
   genuinely isolated item from the original three-item list (item 4),
   if concrete forward progress is wanted on something *other* than the
   Dialogue design conversation itself. No dependency on audio/clock
   questions at all.
3. Everything else from the original item-4 list (Route Graph connections
   → real `<ROUTE>` elements) stays held with the above, same reasoning
   as before.

---

## 4. Loose threads, named so they aren't lost

- **`cultivar_Cindy.xml` picked up fresh data via "Refresh from API," not
  via a plain page reload.** Not chased down this session — worth a look
  whenever cultivar-loading is back in view, since a plain reload feels
  like it should also work and currently doesn't.
- **The Events Editor's open-cue-panel doesn't auto-refresh** when fresh
  `mccf_scene_data` arrives — if a Gesture cue panel is already open when
  `AGENT_CLIPS` updates in the background, the dropdown shown doesn't
  update until the cue is reselected. Confirmed via code reading; not
  confirmed to actually matter in practice (the live test that mattered
  today was resolved by "Refresh from API" alone). Small, low-risk,
  whenever it's relevant.
- **`zone_affinity` clobber risk** in `mccf_cultivar_lambda.py`'s JSON
  POST path — full-object reconstruction from the payload, and Character
  Creator's payload never includes `zone_affinity`, so saving a character
  there would silently reset it to empty if it's ever set through a
  different path. Flagged, not fixed — same shape of bug as the
  `receptivity` one below, not yet demonstrated as *actually* happening
  the way receptivity was.
- **`receptivity` still isn't in `saveCharacter()`'s main payload** —
  confirmed, demonstrated live (a real save visibly dropped a cultivar's
  `<Receptivity>` element entirely this session). Same shape of fix as
  `behavior_clips` was. Not done — stayed out of scope on purpose while
  chasing the clips bug specifically.
- **The standing "gain sliders have never worked" bug** — still not
  traced. Carried over from Day 82.
- **Avatar proto-interface gap** — Character Creator still has no
  declared `ProtoInterface` for gestures; `timerDEF` string convention
  only. Carried over from Day 82.
- **`cv_conditions`** — still authored, persisted, never consumed at
  runtime. One relevant new fact from this session: the cultivar schema's
  EBPS min/max bounds per clip (`E_min`/`E_max`/etc.) are confirmed real
  and already round-trip correctly through `mccf_cultivar_lambda.py` —
  the data contract isn't just planned, it's live and working. Only the
  "consume it at runtime" half is still missing.
- **Zone-radius-based audio distance falloff** — still just named as
  wanted, no design work done. Carried over from Day 82.
- **H-Anim Editor pose-slider / Mixamo-Blender ingest distortion** —
  explicitly backburnered by direct instruction, not touched this
  session. Now has a concrete, first-hand-tested lead attached for
  whenever it's back in scope: a specific export order (Tripo FBX → Mixamo
  FBX → Blender → GLB) that resolved an identical corruption symptom for
  someone else's real pipeline, plus a reminder that Tripo-generated mesh
  weight (~1.9M faces in the one example tested) will need decimation
  before real-time use regardless of the rigging/correspondence question.
