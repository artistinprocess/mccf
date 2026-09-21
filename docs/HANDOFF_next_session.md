# MCCF Session Handoff — H-Anim Facial System + EBPS Architecture

Technical summary only. Covers: what's confirmed working, what got fixed,
what's still open, and the immediate next steps (Blender smoothing pass,
then Cindy).

---

## 1. What's confirmed working

- **H-Anim facial displacement mechanism, proven**: `HAnimDisplacer` as a
  direct child of `HAnimJoint`, `coordIndex` sparse into
  `HAnimHumanoid.skinCoord`, driven by a plain `weight` field — no
  `HAnimSegment`, no mesh segmentation, no Script required. Confirmed
  against the W3DC reference example, confirmed in writing by John
  Carlson (H-Anim WG), confirmed live on Anna's own mesh.
- **Anna has 9 real AU displacers built and live** (from
  `anna_au_deltas.json`, real Blender shape-key data, not synthetic):
  `AU1_InnerBrowRaiser`, `AU2_OuterBrowRaiser`, `AU4_BrowLowerer`,
  `AU5_UpperLidRaiser` (all four split `_l_displacer`/`_r_displacer` —
  she has separate `l_eyebrow_joint`/`r_eyebrow_joint` and
  `l_eyelid_joint`/`r_eyelid_joint`), plus `AU6_CheekRaiser`,
  `AU9_NoseWrinkler`, `AU12_LipCornerPuller`, `AU15_LipCornerDepressor`
  (single, parented under `Head` — no dedicated cheek/nose/mouth joint
  exists in her rig) and `AU26_JawDrop_LipCorrective` (single, under
  `temporomandibular`). All verified: every one of the 4,402 real
  vertex deltas landed exactly once, no loss, no duplication.
- **Naming convention, locked in and matching across every consumer**:
  `<AUName>_displacer` (unilateral) or `<AUName>_l_displacer` /
  `<AUName>_r_displacer` (bilateral, only when two joints actually exist
  to host each side). Both the live preview driver
  (`avatar_preview()` in `mccf_hanim_api.py`) and the export writer
  (`_update_displacer_weights()`) use this exact convention.
- **Cultivar vs. character, now structurally real, not just conceptual**:
  a cultivar is a stateless, re-testable template
  (`CultivarDefinition.weights`); a character is pure accumulated
  history (`AgentRuntimeState` + `Agent`/`CoherenceRecord`). Testing a
  cultivar via the Constitutional tool and playing a live character of
  the same name can no longer collide, at either the φ/ε layer or the
  underlying coherence-history layer.
- **Gesture playback and Stop both work**, avatar-agnostic — no
  hardcoded timer names anywhere in the driver.
- **Dialogue Editor can now generate improv lines and batch-persist
  EBPS**, as two genuinely separate, on-demand actions (generate →
  author edits the chatty LLM output → explicit persist), producing a
  real `/arc/export` file — the first real queryable historical EBPS
  data for a dialogue scene, not just an in-editor display.
- **The historical Constitutional-tool result ("Llama returns to
  baseline") is unaffected by any bug found this session** — verified,
  not assumed: it reads `/arc/record`'s own returned `cv`, never
  `observed_cv`/`AgentRuntimeState`.

## 2. Bugs found and fixed this session

1. `_animTimersStopped` undefined in `avatar_preview()` — broke all
   gesture playback (strict-mode ES module, threw on every
   `enableTimer` call before reaching `timer.enabled = true`). Fixed.
2. `disableAllTimers` had a hardcoded, wrong-for-Tripo timer-name list —
   Stop only ever worked on `Timer1`. Now tracks whatever `enableTimer`
   actually turned on; no naming convention assumed for any avatar.
3. `DisplacerTestTimer` self-looping in `Anna_displacer_test2.x3d` —
   disabled. Test artifacts (`l_eyebrow_raise_test`,
   `DisplacerTestTimer`, `DisplacerTestInterp`, their ROUTEs) removed
   entirely when the 9 real displacers were built.
4. `AgentRuntimeState.set_constitutional()` initialized `expressive_cv`
   (ϵ) equal to `constitutional_cv` (φ) instead of zeros. Since
   `observed_cv = φ + ϵ`, this doubled every character's observed state
   immediately after every `/arc/record` call, for every regulation
   level — including regulation=1.0, whose entire defined guarantee is
   "ϵ locked to zero, pure constitutional state." Confirmed against the
   original written spec and against `mccf_couplers.py`'s own Damping
   coupler invariant. Fixed to initialize to zeros.
5. `_agent_runtime` (the φ/ε registry) was keyed by bare name — a
   cultivar-test run and a live character of the same name shared a
   slot. Fixed: composite `scope::name` key (`_rt_key()`), defaults to
   `'character'` everywhere except the Constitutional tool, which now
   explicitly sends `scope: 'cultivar_test'`.
6. Deeper version of the same bug, one layer down: `field.agents` (the
   `Agent`/`CoherenceRecord` coherence-history registry, in
   `mccf_core.py`) was a single global instance with no scope concept
   at all — same collision, at the layer `weighted_coherence()` and
   `classify_arc_genre()` actually run on. Fixed: a second, separate
   `CoherenceField` instance (`field_test`), `arc_record()` picks
   `field_obj = field_test if scope=='cultivar_test' else field`.
7. `_arc_coherence_history` (feeds `classify_arc_genre`) had the same
   bare-name-key collision. Fixed with the same `_rt_key()` composite
   key, in `arc_record`, `_compute_arc_residue`, `couplers_tick`'s
   phase-transition backfill, and `arc_residue`.

## 3. Found, confirmed, NOT yet fixed

- **`/voice/speak`'s `record_to_field: true` write bypasses scope
  entirely.** `voice_bp.field` is hardcoded once at server startup —
  `voice_bp.field = field` (character scope), permanently. When the
  Constitutional tool uses an LLM-linked answer, `/voice/speak` writes
  a real (simplified, sentiment-only) coherence interaction straight
  into the live character field, regardless of the `cultivar_test`
  scope sent to the follow-up `/arc/record` call. Confirmed this is the
  same behavior in the original waypoint version — not a regression,
  a pre-existing gap surfaced by this session's isolation work.
  **Decided fix, not yet applied**: have `mccf_constitutional.html`
  send `record_to_field: false` on its `/voice/speak` calls, relying
  entirely on the already-correct `/arc/record` call for persistence.
  One line, in the modal's `fetch(API + '/voice/speak', ...)` body.
- Scene Composer's own Record Arc mode also uses `/voice/speak` with
  `record_to_field: true` — this is *correct* there (it's always
  character scope, never cultivar_test), left alone deliberately.

## 4. Real, deliberately deferred work (not urgent, don't start yet)

- **Series Editor / checkpoint-graph continuity** across non-contiguous
  scenes (ordered / unordered / flashback edges between per-character
  checkpoints). Explicitly deferred until after the demo, per your own
  call — single-scene runs only for now. `/arc/residue` already exists
  as a narrow, working precursor (one flat salience-weighted residue
  blended into a scene start, opt-in via `<Continuity/>`) — worth
  knowing it's there when this work resumes.
- **`EBPSToDisplacer` connector** (the bare-Script SAI connector that
  drives a displacer's `weight` from a live EBPS value) — designed
  (direct-to-displacer, no `FaceController` intermediary, per the
  architecture decision early this session) but never built.
- **Character Creator's `_discoverFaceCoords()`** still only recognizes
  the old `Coord_<region>` pattern, not `HAnimDisplacer` — cosmetic
  (the mechanism works regardless), low priority.
- **EBPS measurement validity** — per today's conversation with Kate:
  P (and E/B/S) are currently lexical bag-of-word proxies
  (`_decompose_to_channels` in `mccf_voice_api.py`), not validated
  measures of the underlying constructs. Two concrete, non-redesign
  validation tests were identified (lexical-P-residual vs. next-step
  authored pressure; partial correlation of P against genre/recovery
  controlling for E/B/S) but not run. Real arc-export data
  (`/arc/export`, now actually reachable from the Dialogue Editor) is
  the substrate whenever that gets picked up again.

## 5. Immediate next steps, in order

1. Smooth Anna's `AU12_LipCornerPuller` (smile) shape key in Blender —
   see the Desktop Claude prompt for this session, provided separately.
2. Re-extract `anna_au_deltas.json` (or at minimum AU12's entry) from
   the smoothed shape key, same method as the original extraction
   (glTF-diff against rest pose, same vertex-index numbering).
3. **The edited mesh does need to come back through the same
   displacer-build process — it will not "just work" out of Sunrize.**
   See the note on this below; don't skip it.
4. Fix the `/voice/speak` `record_to_field` bypass (§3) — small, whenever
   convenient, not blocking anything.
5. Cindy: confirm her actual `HAnimJoint` set once her rig exists (don't
   assume it matches Anna's — check it, the way Anna's was checked),
   then decide which of the 29 possible AUs to hand-sculpt. See the
   AU list and recommendation given separately.
