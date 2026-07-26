# MCCF Day 76 — Seed for Day 77

*Written after a full design session covering dialogue/Chorus LLM voice, avatar camera
rigs, the camera live-preview bug, and Place-module consolidation. This was reconciliation-
and-decision work, not implementation — no code was written this session. Four companion
documents came out of it, listed below. This doc is the index and the settled-decision
summary; the companion docs carry the actual detail. Treat this the way Day 75's seed
doc treated `MCCF_Scene_Integration_Spec_v0.1.md` — read the seed first, pull the
companion doc only for the section you're actually working on.*

## Status banner

- ✅ **Dialogue/Chorus LLM voice mechanism — settled.** One shared character-voice
  mechanism, two trigger points (regular dialogue's `mode="improv"` Line vs. Chorus's
  scene-scoped `arc-complete` firing). Blank-Response-triggers-LLM is dead — explicit
  `mode` only. See `MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md`.
- ✅ **`dialogue-xml.js`/`dispatcher.js` read in full, confirmed against the design
  above.** `mode: 'improv'` already exists in the real schema (not the `mode="llm"`
  originally proposed — corrected in the companion doc). `arc-complete` trigger fully
  implemented in both files. `legacy-waypoint` migration path already exists. One real,
  confirmed gap: `dispatcher.js`'s `fireArcComplete()` and `mccf_chorus.py`'s
  `fire_chorus()` were built independently and have never been wired together.
- ✅ **Avatar camera rig / discard-and-reauthor decision — settled.** Inherited
  avatar-authored cameras (confirmed broken/unparented in `cindy_hanim.x3d`) are
  discarded, not migrated. Character Creator becomes the place authors build a real
  parented camera rig per avatar file. A "version" of a character = a separate `.x3d`
  file in the avatars directory, selected independently of Cultivar identity in the
  Agents tab (matches existing Swap Avatar UI). Discovery is a cheap, baked-at-save-time
  **XML** manifest (not JSON — corrected from an earlier draft; XML was an early project
  decision, sits as a sidecar next to the `.x3d`, reuses `field-map.js`'s own
  `<MetadataSet>` house style). No Composer-side generic fallback rig — Character-
  Creator-authored is the only source, to avoid polluting the X_ITE viewpoint menu with
  near-duplicate generic cameras per avatar. See
  `MCCF_Avatar_Camera_Rig_Manifest_Spec_v0.1.md`.
- ✅ **Scene composition ordering, confirmed as a real data dependency, not a UI
  nicety.** Character Creator defines capability → Agents tab assigns which avatar
  version is in the scene → Events/Dialogue can only discover triggers for what's
  actually present. No hard enforcement needed — an unassigned agent already gets a
  placeholder in the existing system; empty dropdowns are a sufficient natural signal.
- ✅ **Camera live-preview bug — root cause found, fix is known, not a research
  question.** The old events editor's preview used `getField().setValue()`, the exact
  SAI pattern Camera Spec v1.3 §4 already proved unreliable and replaced with direct
  property assignment in the Loader's working camera code. Fix: salvage the position
  math as-is, rewrite only the SAI write path using the already-proven pattern, add
  real teardown (destroy-on-close) instead of the existing same-src-only guard. See
  `MCCF_Scene_Placement_Module_Consolidation_v0.1.md` §1.
- ✅ **Place-module consolidation — settled, camera-first.** Cameras/lights/FX/assets
  stop being separate placement tools; one consolidated module, extending the existing
  Zones/Waypoints/Paths/Cameras precedent. V1 is camera-only. Right-panel inconsistency
  across today's sub-modules (needed a `clearSel()` workaround) is a confirmed real
  problem to fix in the consolidation, not carry forward. Zone-cultivar pattern (reusable
  zone type across scenes, same shape as Character Cultivars) is the precedent to reuse
  for a future "light cultivar." See `MCCF_Scene_Placement_Module_Consolidation_v0.1.md`.
- ✅ **Lighting draft spec reviewed and corrected.** §4's X_ITE-correction research
  scope widened from "field-access asymmetry" to the full Camera Spec §4 correction set
  (all five gotchas). §6's zone-affect-biased light idea corrected from "speculative" to
  "already-proven pattern" — it's the identical shape to `SCENE_FOG`'s existing
  `affect-writable`/`channel`/`curve`/`arbitration` manifest, already shipping. §7's
  tab-placement question cross-referenced to the now-settled Place Module Consolidation
  decision instead of left open. Still correctly pre-design otherwise — no class model,
  no proto names, research pass not yet done. See
  `MCCF_Lighting_System_Spec_v0.1_DRAFT.md` (Day 76 revision).
- ⬜ **No code written this session.** Everything above is decided, cross-checked
  against real source (composer HTML, both prototype editors, the full dispatcher/
  dialogue/field-map/timeline-xml/worked-manifests JS, camera protos, an actual avatar
  file, Character Creator), and written down — but none of it is implemented yet.

---

## 1. Companion documents from this session

- `MCCF_Dialogue_Chorus_LLM_Voice_Spec_v0.1.md` — LLM character-voice mechanism,
  `mode="improv"`, Chorus's `voice_actor`/captured-lines path, the confirmed
  `arc-complete`↔Chorus wiring gap.
- `MCCF_Avatar_Camera_Rig_Manifest_Spec_v0.1.md` — discard-inherited-cameras decision,
  Character-Creator-authored rigs, XML sidecar manifest format, avatar-versioning model,
  the still-open scene-level default-bind-viewpoint problem (§5 of that doc).
- `MCCF_Scene_Placement_Module_Consolidation_v0.1.md` — camera live-preview root cause
  and fix, the single-Place-module decision, current Place-tab architecture notes
  (zone cultivar, right-panel inconsistency), camera-first scope.
- `MCCF_Lighting_System_Spec_v0.1_DRAFT.md` (Day 76 revision) — still pre-design on
  purpose; corrections folded in, research pass not yet run.

## 2. Files now confirmed in hand and read in full this session

Carry forward, no need to re-request:
- `mccf_scene_composer.html` (full 5035-line file — Place tab, Events/Character Creator
  iframe bridges, camera placement code, grid/consolidation history all traced)
- `mccf_events_editor_prototype_2.html` (old events editor — camera shot vocabulary,
  broken SAI preview pattern, WebGL teardown guard, all confirmed directly in source)
- `mccf_timeline_dialogue_prototype_v2.html` (new Timeline/Dialogue prototype shell)
- `dispatcher.js`, `dialogue-xml.js`, `field-map.js`, `timeline-xml.js`,
  `worked-manifests.js` — all read in full, not inferred from comments
- `mccf_chorus.py` — read in full, `voice_actor`/captured-lines path understood
- `MCCF_Camera_System_Spec_v1_3.md` — read in full
- `mccf_camera_protos.x3d` — read in full (`AgentOrbitCamera`, `FreeCamera`,
  `AgentTrackCamera` — confirmed more advanced than Camera Spec v1.3 §9 admits)
- `mccf_character_creator.html` — read; confirmed zero camera/viewpoint handling today
- `cindy_hanim.x3d` — read; confirmed the actual broken unparented-camera pattern this
  whole avatar-rig decision is based on
- `MCCF_Lighting_System_Spec_v0.1_DRAFT.md` — read and revised this session

## 3. Open items for Day 77, ranked

1. **Confirm the grid-placement live bug directly.** Still unresolved from earlier this
   session: does the *current* Place→Cameras panel actually fail to persist angle/
   height live, or was that memory of the old events editor's version? The source read
   suggests the current panel is correctly wired end-to-end — this needs an actual
   in-browser check to settle, not another source read.
2. **Scene-level default-viewpoint bind field.** X3D's binding-stack semantics bind
   whichever Viewpoint is first in document order on load — never authorial intent here,
   worse as more Viewpoints accumulate per scene (per-avatar rigs + free cameras +
   overview). Needs a schema field (`MCCF_Avatar_Camera_Rig_Manifest_Spec_v0.1.md` §5)
   and a Loader-side explicit-bind-on-ready implementation. Not designed yet.
3. **Wire `dispatcher.js`'s `fireArcComplete()` to `mccf_chorus.py`'s `fire_chorus()`.**
   Confirmed real, scoped, not a design question — both sides already exist and
   anticipate each other in their own comments.
4. **Character-voice prompt builder.** `character_voice_prompt(actor_id, scene_context)`
   doesn't exist anywhere yet — needs to live in Python alongside Chorus's existing LLM
   dispatch code, pulling from a Cultivar's real Disposition/Weights/FailureMode/Phrases
   rather than Chorus's current `persona`/`tone` strings.
5. **Camera-rig manifest implementation.** XML sidecar format decided; the actual
   `<MetadataSet name='cameraRig'>` field shape (what exactly gets listed per Viewpoint)
   isn't drafted yet.
6. **Lighting research pass.** `MCCF_Lighting_System_Spec_v0.1_DRAFT.md` §4's list —
   `OrientationInterpolator`, Followers component, `ComposedShader`, empirical light-
   count ceiling — needs someone actually driving a live X_ITE session. Not source-
   readable; needs the browser open, same as the original `agent_orbit` debugging did.
7. **Right-panel standardization shape.** Principle settled (one pattern, not several);
   the actual shared field/shape design for the consolidated Place module's inspector
   isn't drafted.
8. **`FreeCamera` cue-fire binding.** Confirmed unwired (placement + export only, per
   the proto file's own comments) — real gap, low priority relative to the above.

## 4. Recommended Day 77 opening move

1. **Settle item 1 first** — five minutes in a real browser answers something four
   companion documents can't.
2. **Pick up item 3 (Chorus↔dispatcher wiring)** as the first real implementation task
   coming out of this session — it's the most concretely scoped, both halves already
   exist, and it's a genuine EBPS-adjacent win (Chorus is explicitly named as "the
   reason we built" this system).
3. Everything else in §3 can proceed in roughly the ranked order, but none of it is
   blocking any of the others the way earlier sessions' open questions were — this
   session's whole point was clearing exactly that kind of blocking ambiguity out.
